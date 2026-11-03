"""Provision a NEW local MySQL 8.0 Docker container without changing existing DBs.

Keeps generated credentials only in ignored .local files / .env (mode 0600).
Re-running reuses the existing container and never resets data or passwords.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.local'
NAME = 'accountpulse-local-mysql'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
env = {k: v for k, v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}


def docker(*args, check=True):
    return subprocess.run([*DOCKER, *args], env=env, text=True, capture_output=True, check=check)


def main():
    STATE.mkdir(exist_ok=True, mode=0o700)
    existing = docker('inspect', NAME, check=False)
    config_path = STATE / 'mysql.env'
    app_env = ROOT / '.env'
    if existing.returncode == 0:
        record = json.loads(existing.stdout)[0]
        if record.get('Config', {}).get('Labels', {}).get('accountpulse.managed') != 'true' or not config_path.exists():
            sys.exit('A container with this name already exists but is not managed by this script. No changes made.')
        if not record['State']['Running']:
            docker('start', NAME)
        print('Existing AccountPulse MySQL container reused. No database records changed.')
        return
    if app_env.exists() or config_path.exists():
        sys.exit('An existing .env or MySQL credential file was found. Use that configuration; no replacement was made.')
    root_password, password = secrets.token_hex(24), secrets.token_hex(24)
    config_path.write_text(f'MYSQL_ROOT_PASSWORD={root_password}\nMYSQL_DATABASE=banking_analysis\nMYSQL_USER=accountpulse\nMYSQL_PASSWORD={password}\n')
    config_path.chmod(0o600)
    result = docker('run', '-d', '--name', NAME, '--label', 'accountpulse.managed=true',
                    '--publish', '127.0.0.1:3306:3306', '--env-file', str(config_path),
                    '--mount', 'type=volume,source=accountpulse-mysql-data,target=/var/lib/mysql',
                    '--restart', 'unless-stopped', 'mysql:8.0', check=False)
    if result.returncode:
        # Keep credential file so a failed provision cannot hide or replace state.
        print(result.stderr, file=sys.stderr)
        sys.exit('Container setup failed. Inspect Docker and .local/mysql.env; existing data was not reset.')
    app_env.write_text(f'SECRET_KEY={secrets.token_hex(32)}\nDATABASE_URL=mysql+pymysql://accountpulse:{password}@127.0.0.1:3306/banking_analysis?charset=utf8mb4\nCOOKIE_SECURE=false\n')
    app_env.chmod(0o600)
    print('Started dedicated MySQL 8.0 container; generated private local .env. Wait for MySQL readiness, then inspect-db and init-db.')


if __name__ == '__main__':
    main()
