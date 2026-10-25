param(
    [string]$Device = 'emulator-5554',
    [string]$AuthApiUrl = 'http://10.0.2.2:3000',
    [string]$AnalysisApiUrl = 'http://10.0.2.2:8000',
    [switch]$RefreshDependencies
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    # No packages changed in this integration. Reuse existing dependencies.
    # Setting FLUTTER_WINDOWS=false does not disable this feature in this SDK.
    if ($RefreshDependencies -or !(Test-Path -LiteralPath '.dart_tool\package_config.json')) {
        flutter pub get
        if ($LASTEXITCODE -ne 0) {
            throw 'Dependency generation failed. If Flutter reports symlink support, enable Windows Developer Mode, then retry -RefreshDependencies. No global settings were changed by this script.'
        }
    }
    flutter run --no-pub -d $Device "--dart-define=HPT_AUTH_API_URL=$AuthApiUrl" "--dart-define=HPT_ANALYSIS_API_URL=$AnalysisApiUrl"
    if ($LASTEXITCODE -ne 0) { throw 'Android launch failed.' }
} finally {
    Pop-Location
}
