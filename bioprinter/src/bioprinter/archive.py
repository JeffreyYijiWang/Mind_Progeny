"""Safe, explicit local image archive ingestion. Never executes archive content."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import hashlib
import json
import stat
import zipfile
from .ingestion import EXTENSIONS, sha256


def extract_images(archive,destination,*,expected_count=None,max_bytes=2_000_000_000):
    archive=Path(archive);destination=Path(destination).resolve()
    records=[];seen=set()
    with zipfile.ZipFile(archive) as source:
        entries=[info for info in source.infolist() if not info.is_dir()]
        if sum(i.file_size for i in entries)>max_bytes: raise ValueError('Archive exceeds extraction size limit')
        if len(entries)>10000: raise ValueError('Too many archive members')
        for info in entries:
            name=PurePosixPath(info.filename)
            # ZipInfo normalizes Windows backslashes and truncates NULs on read;
            # validate its original header name as well as its resolved target.
            if ('\\' in info.orig_filename or '\0' in info.orig_filename or name.is_absolute()
                or any(p in {'..','.'} or ':' in p or p!=p.rstrip(' .') or PureWindowsPath(p).is_reserved() for p in name.parts)):
                raise ValueError('Unsafe archive path: '+info.filename)
            if stat.S_ISLNK(info.external_attr>>16): raise ValueError('Archive symlinks are unsupported')
            target=(destination/Path(*name.parts)).resolve()
            if not target.is_relative_to(destination): raise ValueError('Archive path escapes destination')
            key=target.as_posix().casefold()
            if key in seen: raise ValueError('Case-insensitive archive filename collision')
            seen.add(key)
            if name.suffix.lower() not in EXTENSIONS: raise ValueError('Unsupported archive member: '+info.filename)
        if expected_count is not None and len(entries)!=expected_count:
            raise ValueError(f'Expected {expected_count} images, found {len(entries)}')
        destination.mkdir(parents=True,exist_ok=False)
        for info in entries:
            target=destination/Path(*PurePosixPath(info.filename).parts);target.parent.mkdir(parents=True,exist_ok=True)
            # Reading verifies the ZIP entry CRC. No ZIP member path is passed to a shell.
            content=source.read(info)
            with target.open('xb') as output: output.write(content)
            records.append({'archive_name':info.filename,'relative_path':target.relative_to(destination).as_posix(),
                            'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
    metadata={'archive':str(archive.resolve()),'archive_sha256':sha256(archive),'image_count':len(records),'images':records}
    (destination.parent/'archive_manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
    return metadata
