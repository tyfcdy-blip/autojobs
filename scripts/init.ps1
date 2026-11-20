param(
    [string]$Name,
    [AllowEmptyString()][string]$Description
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion -lt [version]'7.3') {
    [Console]::Error.WriteLine('PowerShell 7.3+ is required. Use python scripts/init_project.py instead.')
    exit 1
}
# 仅在脚本作用域使用标准参数传递，保留引号且不改变调用者设置。
$PSNativeCommandArgumentPassing = 'Standard'
$initializerPath = Join-Path $PSScriptRoot 'init_project.py'
$initializerArguments = @($initializerPath)
if ($PSBoundParameters.ContainsKey('Name')) {
    $initializerArguments += "--name=$Name"
}
if ($PSBoundParameters.ContainsKey('Description')) {
    $initializerArguments += "--description=$Description"
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python @initializerArguments
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @initializerArguments
} else {
    Write-Error 'Python 3.11+ is required. Install Python and run this script again.'
    exit 1
}
exit $LASTEXITCODE
