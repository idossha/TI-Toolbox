# Enable Long Path Support on Windows
# This script must be run as Administrator

Write-Host "🔧 TI-CSC: Enabling Long Path Support on Windows" -ForegroundColor Cyan
Write-Host "=" * 50

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "   Right-click on PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "✅ Running with Administrator privileges" -ForegroundColor Green

# Enable long path support in Windows
try {
    Write-Host "🔧 Enabling long path support in registry..." -ForegroundColor Yellow
    
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem"
    $regName = "LongPathsEnabled"
    $regValue = 1
    
    # Check current value
    $currentValue = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
    
    if ($currentValue.$regName -eq 1) {
        Write-Host "✅ Long path support is already enabled!" -ForegroundColor Green
    } else {
        # Enable long path support
        Set-ItemProperty -Path $regPath -Name $regName -Value $regValue -Type DWord
        Write-Host "✅ Long path support enabled successfully!" -ForegroundColor Green
        Write-Host "⚠️  A system restart may be required for changes to take effect" -ForegroundColor Yellow
    }
    
    # Also enable for Git (optional)
    try {
        Write-Host "🔧 Enabling long path support for Git..." -ForegroundColor Yellow
        git config --system core.longpaths true 2>$null
        Write-Host "✅ Git long path support enabled" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Could not configure Git (this is optional)" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "❌ Failed to enable long path support: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "🎉 Configuration completed successfully!" -ForegroundColor Green
Write-Host "   You can now try running the build script again:" -ForegroundColor White
Write-Host "   python3 .\build.py" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to continue" 