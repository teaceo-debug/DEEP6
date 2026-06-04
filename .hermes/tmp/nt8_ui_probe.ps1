$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$p = Get-Process -Name 'NinjaTrader' | Select-Object -First 1
if (-not $p) {
    Write-Host 'NO-NT8'
    exit 1
}

$pidCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
    [int]$p.Id
)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
    [System.Windows.Automation.TreeScope]::Children,
    $pidCond
)
Write-Host "windows=$($wins.Count)"

foreach ($w in $wins) {
    $wName = ''
    try { $wName = $w.Current.Name } catch {}
    Write-Host "WINDOW: [$wName]"
    try {
        $desc = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        Write-Host "desc=$($desc.Count)"
        $hits = New-Object System.Collections.Generic.List[string]
        foreach ($el in $desc) {
            $name = ''
            $aid = ''
            try { $name = $el.Current.Name } catch {}
            try { $aid = $el.Current.AutomationId } catch {}
            if ($name -match 'CS\d{4}|error|warning|\.cs|NinjaScript|Output|compile' -or $aid -match 'error|output|ninja|compile') {
                $hits.Add(($name + ' || ' + $aid))
            }
        }
        $hits | Select-Object -Unique -First 80 | ForEach-Object { Write-Host $_ }
    } catch {
        Write-Host 'ERR'
    }
}