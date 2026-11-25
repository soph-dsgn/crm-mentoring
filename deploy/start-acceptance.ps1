[CmdletBinding()]
param([string]$OpenSsl)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $PSScriptRoot 'compose.acceptance.yml'
$certDir = Join-Path $repo 'private/acceptance-tls'
$cert = Join-Path $certDir 'localhost.crt'
$key = Join-Path $certDir 'localhost.key'

if (!(Test-Path -LiteralPath $cert) -or !(Test-Path -LiteralPath $key)) {
    if (!$OpenSsl) {
        $executable = Get-Command openssl.exe -ErrorAction SilentlyContinue
        if ($executable) {
            $OpenSsl = $executable.Source
        } else {
            $git = (Get-Command git.exe).Source
            $OpenSsl = Join-Path (Split-Path -Parent (Split-Path -Parent $git)) 'usr/bin/openssl.exe'
        }
    }
    New-Item -ItemType Directory -Path $certDir -Force | Out-Null
    & $OpenSsl req -x509 -newkey rsa:2048 -nodes -days 365 -keyout $key -out $cert -config (Join-Path $PSScriptRoot 'acceptance-tls.cnf')
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать локальный сертификат HTTPS' }
}

docker compose -f $compose build
if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать образы' }
docker compose -f $compose up -d --wait database
if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить тестовую базу' }
docker compose -f $compose run --rm --no-deps backend alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Не удалось обновить схему тестовой базы' }
docker compose -f $compose up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить тестовую Кураторскую' }
Write-Output 'https://localhost:8443'
