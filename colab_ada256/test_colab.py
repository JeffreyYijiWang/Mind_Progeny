"""Offline tests. No Colab login, Drive mount, GPU initialization or GAN run."""
import ast
import base64
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

os.environ['CUDA_VISIBLE_DEVICES'] = ''
import cloud_runner as cloud
ROOT = Path(__file__).resolve().parent
LOCAL = ROOT.parent / 'stylegan2_ada'


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scratch = self.root / 'scratch'
        self.drive = self.root / 'project/runs/example'
        self.scratch.mkdir()
        self.drive.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, step):
        source = self.scratch / f'network-snapshot-{step:06d}.pkl'
        source.write_bytes(f'CPU fixture {step}'.encode())
        return source

    def test_publication_roundtrip_and_corruption_rejection(self):
        self.snapshot(1)
        path = cloud.publish_snapshots(self.scratch, self.drive)[0]
        project = self.drive.parent.parent
        self.assertEqual(cloud.verified_snapshot(project, path), path)
        path.write_bytes(b'broken')
        with self.assertRaises(IOError):
            cloud.verified_snapshot(project, path)
        with self.assertRaises(IOError):
            cloud.publish_snapshots(self.scratch, self.drive)
        self.assertTrue((self.scratch / 'network-snapshot-000001.pkl').exists())

    def test_copy_failure_leaves_local_and_publishes_no_receipt(self):
        source = self.snapshot(1)
        with patch.object(cloud, 'verified_copy', side_effect=IOError('simulated Drive quota failure')):
            with self.assertRaises(IOError):
                cloud.publish_snapshots(self.scratch, self.drive)
        self.assertTrue(source.exists())
        self.assertEqual(list(self.drive.glob('*.verified.json')), [])

    def test_retention_latest_four_and_ten_kimg_milestones(self):
        for kimg in range(1, 16):
            self.snapshot(kimg)
            cloud.publish_snapshots(self.scratch, self.drive)
        kept = {cloud.read(p)['kimg_floor'] for p in self.drive.glob('*.verified.json')}
        self.assertEqual(kept, {10, 12, 13, 14, 15})
        self.assertEqual(len(list(self.scratch.glob('*.pkl'))), 2)

    def test_exclusive_lock_and_cleanup(self):
        project = self.root / 'lock-project'
        with cloud.lock(project):
            with self.assertRaises(RuntimeError):
                with cloud.lock(project):
                    pass
        self.assertFalse((project / 'writer.lock').exists())

    def test_lock_recovery_requires_confirmation_and_rejects_live_pid(self):
        project = self.root / 'lock-project'
        with cloud.lock(project):
            owner = cloud.read(project / 'writer.lock/owner.json')
            with self.assertRaises(ValueError):
                cloud.release_lock(project, owner['token'], '')
            with self.assertRaises(RuntimeError):
                cloud.release_lock(project, owner['token'], 'I stopped the old Colab runtime')

    def test_no_execute_never_reaches_cloud_or_model(self):
        with patch.object(cloud, 'require_cloud', side_effect=AssertionError('should not get this far')):
            with self.assertRaisesRegex(RuntimeError, 'Training is off'):
                cloud.train_model(self.root, {}, False)
            with self.assertRaisesRegex(RuntimeError, 'Generation is off'):
                cloud.generate(self.root, {}, False, None, [], 'cuda')


class NotebookTests(unittest.TestCase):
    def test_cells_compile_payload_checksums_and_execution_defaults(self):
        notebook = cloud.read(ROOT / 'NeoHuman_ADA256_Colab.ipynb')
        assignments = {}
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                self.assertIsNone(cell['execution_count'])
                self.assertEqual(cell['outputs'], [])
                source = ''.join(cell['source'])
                compile(source, '<colab-cell>', 'exec')
                for node in ast.parse(source).body:
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                assignments[target.id] = node.value.value
        for name in ('START_TRAINING', 'GENERATE', 'CONFIRM_OLD_RUNTIME_STOPPED', 'CLEAR_PREVIOUS_STOP_REQUEST'):
            self.assertIs(assignments[name], False)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(assignments['PAYLOAD']))) as z:
            self.assertEqual(z.read('cloud_runner.py'), (ROOT / 'cloud_runner.py').read_bytes())
            self.assertEqual(z.read('compat.py'), (LOCAL / 'compat.py').read_bytes())
            self.assertEqual(z.read('gpu_policy.py'), (LOCAL / 'gpu_policy.py').read_bytes())
            self.assertEqual(cloud.hashlib.sha256(z.read('neohuman45-256.zip')).hexdigest(), cloud.DATA_SHA)
            self.assertEqual(json.loads(z.read('dataset-manifest.json'))['count'], 45)


class CPUPlanTests(unittest.TestCase):
    def test_actual_upstream_configuration_without_model_or_cuda(self):
        sys.path.insert(0, str(LOCAL))
        sys.path.insert(0, str(LOCAL / 'vendor/stylegan2-ada-pytorch'))
        import torch
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory() as temporary:
            here = Path(temporary)
            shutil.copyfile(LOCAL / 'data/neohuman45-256.zip', here / 'neohuman45-256.zip')
            # Hard link avoids duplicating the 296 MB file; no pickle is loaded.
            os.link(LOCAL / 'weights/ffhq256.pkl', here / 'ffhq256.pkl')
            cfg = {'total_kimg': 100, 'microbatch': 4, 'session_hours': 2}
            with patch.object(cloud, 'HERE', here), \
                 patch.object(cloud.subprocess, 'check_output', side_effect=[cloud.COMMIT, '']), \
                 patch.object(torch.cuda, '_lazy_init', side_effect=AssertionError('CUDA forbidden')):
                args = cloud.options(cfg)
                self.assertEqual(args.training_set_kwargs.resolution, 256)
                self.assertEqual(args.training_set_kwargs.max_size, 45)
                self.assertEqual((args.batch_gpu, args.batch_size), (4, 8))
                self.assertEqual(args.G_kwargs.synthesis_kwargs.channel_base, 16384)
                self.assertTrue(args.allow_tf32)
                self.assertEqual(args.loss_kwargs.pl_batch_shrink, 2)
                self.assertEqual(args.metrics, [])
        self.assertFalse(torch.cuda.is_initialized())


if __name__ == '__main__':
    unittest.main(verbosity=2)
