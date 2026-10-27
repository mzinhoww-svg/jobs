import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    token_file: Path
    allowed_hosts: tuple[str, ...]
    chromium: str = '/usr/bin/chromium'

    def validate(self):
        root = Path(__file__).resolve().parents[1]
        data = self.data_dir.resolve()
        if data == root or data.is_relative_to(root):
            raise ValueError('DATA_DIR_MUST_BE_OUTSIDE_CHECKOUT')
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        if stat.S_IMODE(data.stat().st_mode) & 0o077:
            data.chmod(0o700)
        if self.token_file.stat().st_mode & 0o077:
            raise ValueError('TOKEN_FILE_MUST_BE_PRIVATE')
        token = self.token_file.read_text().strip()
        if len(token) < 32:
            raise ValueError('TOKEN_TOO_SHORT')
        return token

    @classmethod
    def from_env(cls):
        os.umask(0o077)
        data=Path(os.environ['JOBS_DATA_DIR'])
        return cls(data,Path(os.environ.get('JOBS_TOKEN_FILE', str(data/'api-token'))),
                   tuple(x.strip().lower() for x in os.environ.get('JOBS_ALLOWED_HOSTS','').split(',') if x.strip()),
                   os.environ.get('JOBS_CHROMIUM','/usr/bin/chromium'))
