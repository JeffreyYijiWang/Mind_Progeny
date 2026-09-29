"""CPU-only safety/configuration/derivative checks; never construct or run a GAN."""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import manage
import gpu_policy


class GPUPolicyTests(unittest.TestCase):
    def test_eight_gib_cap(self):
        policy = manage.config()["gpu"]
        result = gpu_policy.budget(8 * gpu_policy.GIB, 8 * gpu_policy.GIB, policy)
        self.assertAlmostEqual(result["allocator_fraction"], 0.85)
        self.assertGreaterEqual(result["reserved_headroom_bytes"], gpu_policy.GIB)

    def test_busy_gpu_reduces_budget(self):
        result = gpu_policy.budget(6 * gpu_policy.GIB, 8 * gpu_policy.GIB, manage.config()["gpu"])
        self.assertEqual(result["allocator_limit_bytes"], 5 * gpu_policy.GIB)

    def test_insufficient_headroom_refuses(self):
        with self.assertRaises(RuntimeError):
            gpu_policy.budget(gpu_policy.GIB, 8 * gpu_policy.GIB, manage.config()["gpu"])

    def test_invalid_limits_rejected(self):
        for change in ({"max_allocator_fraction": 1.0}, {"reserve_mib": 0}, {"max_allocator_fraction": float('nan')}):
            with self.assertRaises(ValueError):
                gpu_policy.validate(dict(manage.config()["gpu"], **change))

    def test_configuration_uses_allocator_cap_without_model(self):
        fake = MagicMock()
        fake.cuda.mem_get_info.return_value = (7 * gpu_policy.GIB, 8 * gpu_policy.GIB)
        result = gpu_policy.configure(fake, manage.config()["gpu"])
        fake.cuda.set_per_process_memory_fraction.assert_called_once_with(0.75, device=0)
        self.assertTrue(fake.backends.cuda.matmul.allow_tf32)
        self.assertTrue(fake.backends.cudnn.allow_tf32)
        self.assertFalse(fake.backends.cudnn.benchmark)
        self.assertEqual(result["allocator_limit_bytes"], 6 * gpu_policy.GIB)


class CompletionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name)
        self.cfg = dict(manage.config(), predecessor=str(self.run))
        manage.write(self.run / "config.json", {"schedule": {"budget_seconds": 86400}})
        self.checkpoint = self.run / "checkpoints/final.pt"
        self.checkpoint.parent.mkdir()
        self.checkpoint.write_bytes(b"test fixture, not a torch pickle")

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, seconds):
        manifest = {"entries": [{"path": "checkpoints/final.pt", "bytes": self.checkpoint.stat().st_size,
                                "sha256": manage.sha(self.checkpoint), "training_seconds": seconds}]}
        manage.write(self.run / "manifest.json", {"manifest": manifest, "sha256": manage.canonical_sha(manifest)})

    def test_early_stop_is_not_completion(self):
        self.manifest(86399)
        self.assertFalse(manage.predecessor_status(self.cfg)[0])

    def test_active_writer_blocks_even_complete_checkpoint(self):
        self.manifest(86400)
        (self.run / "writer.lock").mkdir()
        self.assertFalse(manage.predecessor_status(self.cfg)[0])

    def test_verified_completed_unlocked_run_is_eligible(self):
        self.manifest(86400.1)
        self.assertTrue(manage.predecessor_status(self.cfg)[0])

    def test_corruption_blocks_completion(self):
        self.manifest(86400)
        self.checkpoint.write_bytes(b"corrupted")
        self.assertFalse(manage.predecessor_status(self.cfg)[0])

    def test_corrupt_manifest_blocks_completion(self):
        self.manifest(86400)
        envelope = manage.read(self.run / "manifest.json")
        envelope["manifest"]["entries"][0]["training_seconds"] += 1
        manage.write(self.run / "manifest.json", envelope)
        self.assertFalse(manage.predecessor_status(self.cfg)[0])

    def test_train_guard_precedes_upstream_or_cuda_import(self):
        self.manifest(10)
        cli = type("CLI", (), {"execute": True, "resume": None})()
        with patch.object(manage, "upstream_args", side_effect=AssertionError("Must not reach model setup")):
            with self.assertRaisesRegex(RuntimeError, "execution is blocked"):
                manage.train_model(self.cfg, cli)

    def test_execute_must_be_explicit(self):
        cli = type("CLI", (), {"execute": False})()
        with self.assertRaisesRegex(RuntimeError, "opt-in"):
            manage.train_model(self.cfg, cli)


class CPUCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manage.check_source()
        sys.path.insert(0, str(manage.VENDOR))
        import torch
        cls.torch = torch
        torch.set_num_threads(1)
        cls.cuda_guard = patch.object(torch.cuda, "_lazy_init", side_effect=AssertionError("GPU access forbidden in preparation tests"))
        cls.cuda_guard.start()
        import compat
        compat.install()

    @classmethod
    def tearDownClass(cls):
        cls.cuda_guard.stop()
        assert not cls.torch.cuda.is_initialized()

    def test_grid_first_and_second_derivatives(self):
        torch = self.torch
        from torch_utils.ops import grid_sample_gradfix
        grid_sample_gradfix.enabled = True
        torch.manual_seed(2)
        x = torch.randn(1, 2, 4, 4, dtype=torch.double, requires_grad=True)
        grid = torch.rand(1, 2, 2, 2, dtype=torch.double) * 1.2 - 0.6
        fn = lambda value: grid_sample_gradfix.grid_sample(value, grid)
        self.assertTrue(torch.autograd.gradcheck(fn, (x,)))
        self.assertTrue(torch.autograd.gradgradcheck(fn, (x,)))

    def test_reference_bias_and_filter_no_compilation(self):
        torch = self.torch
        from torch_utils.ops import bias_act, upfirdn2d
        x = torch.randn(1, 2, 4, 4, dtype=torch.double, requires_grad=True)
        f = upfirdn2d.setup_filter([1, 3, 3, 1])
        with patch.object(bias_act, "_init", side_effect=AssertionError("No CUDA extension builds")), \
             patch.object(upfirdn2d, "_init", side_effect=AssertionError("No CUDA extension builds")):
            out = bias_act.bias_act(x, act="lrelu")
            out = upfirdn2d.upsample2d(out, f)
            torch.autograd.grad(out.square().sum(), x, create_graph=True)[0].sum().backward()
            self.assertTrue(torch.isfinite(x.grad).all())

    def test_native_convolution_supports_r1_weight_derivative(self):
        torch = self.torch
        from torch_utils.ops import conv2d_gradfix
        conv2d_gradfix.enabled = True
        x = torch.randn(1, 2, 4, 4, requires_grad=True)
        w = torch.randn(3, 2, 3, 3, requires_grad=True)
        out = conv2d_gradfix.conv2d(x, w)
        with conv2d_gradfix.no_weight_gradients():
            image_grad = torch.autograd.grad(out.sum(), x, create_graph=True)[0]
        penalty = image_grad.square().sum()
        weight_grad = torch.autograd.grad(penalty, w)[0]
        self.assertTrue(torch.isfinite(weight_grad).all())
        self.assertGreater(weight_grad.abs().sum().item(), 0)

    def test_ada_transform_chain_supports_input_gradient_penalty(self):
        torch = self.torch
        from training.augment import AugmentPipe
        from torch_utils.ops import grid_sample_gradfix
        grid_sample_gradfix.enabled = True
        torch.manual_seed(17)
        transform = AugmentPipe(xint=1, scale=1, xfrac=1)
        transform.p.fill_(1)
        pixels = torch.randn(1, 3, 16, 16, requires_grad=True)
        coefficient = torch.tensor(0.7, requires_grad=True)
        transformed = transform(pixels)
        gradient = torch.autograd.grad((transformed * coefficient).sum(), pixels, create_graph=True)[0]
        derivative = torch.autograd.grad(gradient.square().sum(), coefficient)[0]
        self.assertTrue(torch.isfinite(derivative))
        self.assertGreater(derivative.abs().item(), 0)

    def test_resolved_microbatch_configuration(self):
        cfg = manage.config()
        with patch("training.training_loop.training_loop", side_effect=AssertionError("No training execution")):
            args = manage.upstream_args(cfg)
        self.assertEqual(args.training_set_kwargs.resolution, 1024)
        self.assertEqual(args.training_set_kwargs.max_size, 45)
        self.assertEqual(args.batch_gpu, 1)
        self.assertEqual(args.batch_size, 4)
        self.assertEqual(args.loss_kwargs.pl_batch_shrink, 1)
        self.assertEqual(args.D_kwargs.epilogue_kwargs.mbstd_group_size, 1)
        self.assertEqual(args.data_loader_kwargs, {"pin_memory": False, "num_workers": 0})
        self.assertEqual(args.metrics, [])
        self.assertTrue(args.allow_tf32)
        self.assertTrue(args.G_kwargs.synthesis_kwargs.fp16_channels_last)
        self.assertTrue(args.D_kwargs.block_kwargs.fp16_channels_last)
        self.assertFalse(args.cudnn_benchmark)
        self.assertFalse(args.training_set_kwargs.xflip)
        for key in ("xflip", "rotate90", "rotate", "aniso"):
            self.assertEqual(args.augment_kwargs[key], 0)
        self.assertFalse(self.torch.cuda.is_initialized())

    def test_256_profile_has_matching_architecture_and_dataset(self):
        cfg = manage.config("256")
        args = manage.upstream_args(cfg)
        self.assertEqual(args.training_set_kwargs.resolution, 256)
        self.assertEqual(args.training_set_kwargs.max_size, 45)
        self.assertEqual((args.batch_gpu, args.batch_size), (4, 8))
        self.assertEqual(args.G_kwargs.synthesis_kwargs.channel_base, 16384)
        self.assertEqual(args.D_kwargs.channel_base, 16384)
        self.assertEqual(args.loss_kwargs.pl_batch_shrink, 2)
        self.assertEqual(args.D_kwargs.epilogue_kwargs.mbstd_group_size, 4)
        self.assertTrue(args.allow_tf32)
        self.assertIn('ffhq256.pkl', args.resume_pkl)
        self.assertNotEqual(cfg['dataset'], manage.config()['dataset'])
        self.assertFalse(self.torch.cuda.is_initialized())


class ResolutionSafetyTests(unittest.TestCase):
    def test_cross_resolution_snapshot_rejected_before_model_load(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / 'runs' / 'example'
            run.mkdir(parents=True)
            snapshot = run / 'network-snapshot-000001.pkl'
            snapshot.write_bytes(b'fixture only')
            manage.write(run / 'config.json', {'resolution': 1024})
            manage.write(snapshot.with_suffix('.verified.json'),
                         {'bytes': snapshot.stat().st_size, 'sha256': manage.sha(snapshot)})
            cfg = manage.config('256')
            with patch.object(manage, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'different resolution'):
                    manage.resolve_snapshot(snapshot, cfg)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            manage.config('512')


if __name__ == "__main__":
    unittest.main(verbosity=2)
