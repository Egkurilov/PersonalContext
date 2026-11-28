"""Fixed, read-only PowerShell query for the active Windows firewall."""

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$pcAddress = $env:PC_FIREWALL_ADDRESS
$pcIp = @(Get-NetIPAddress -IPAddress $pcAddress | Where-Object { $_.AddressState -eq 'Preferred' })
if ($pcIp.Count -ne 1) { throw 'interface unavailable' }
$pcAdapter = @(Get-NetAdapter -InterfaceIndex $pcIp[0].InterfaceIndex)
if ($pcAdapter.Count -ne 1 -or $pcAdapter[0].HardwareInterface -ne $true -or
    $pcAdapter[0].Status.ToString() -ne 'Up') { throw 'physical interface unavailable' }
$pcConnections = @(Get-NetConnectionProfile -InterfaceIndex $pcIp[0].InterfaceIndex)
if ($pcConnections.Count -ne 1) { throw 'profile unavailable' }
$pcName = $pcConnections[0].NetworkCategory.ToString()
if ($pcName -eq 'DomainAuthenticated') { $pcName = 'Domain' }
if ($pcName -notin @('Domain','Private','Public')) { throw 'profile unavailable' }
$pcProfile = @(Get-NetFirewallProfile -PolicyStore ActiveStore -Name $pcName)
if ($pcProfile.Count -ne 1) { throw 'profile unavailable' }
$pcDisabled = @($pcProfile[0].DisabledInterfaceAliases | Where-Object { $null -ne $_ -and $_ -ne '' })
$pcRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Enabled True -Action Allow)
if ($pcRules.Count -gt 4096) { throw 'rule limit' }
function New-PcIndex($pcFilters) {
    $pcIndex = @{}
    foreach ($pcFilter in $pcFilters) {
        $pcId = $pcFilter.InstanceID
        if ([string]::IsNullOrEmpty($pcId) -or $pcIndex.ContainsKey($pcId)) { throw 'ambiguous filters' }
        $pcIndex[$pcId] = $pcFilter
    }
    return ,$pcIndex
}
$pcPorts = New-PcIndex @($pcRules | Get-NetFirewallPortFilter)
$pcAddrs = New-PcIndex @($pcRules | Get-NetFirewallAddressFilter)
$pcApps = New-PcIndex @($pcRules | Get-NetFirewallApplicationFilter)
$pcServices = New-PcIndex @($pcRules | Get-NetFirewallServiceFilter)
$pcInterfaces = New-PcIndex @($pcRules | Get-NetFirewallInterfaceFilter)
$pcTypes = New-PcIndex @($pcRules | Get-NetFirewallInterfaceTypeFilter)
$pcSecurityFilters = New-PcIndex @($pcRules | Get-NetFirewallSecurityFilter)
$pcItems = foreach ($pcRule in $pcRules) {
    $pcId = $pcRule.InstanceID
    if (-not $pcPorts.ContainsKey($pcId) -or -not $pcAddrs.ContainsKey($pcId) -or -not $pcApps.ContainsKey($pcId) -or
        -not $pcServices.ContainsKey($pcId) -or -not $pcInterfaces.ContainsKey($pcId) -or
        -not $pcTypes.ContainsKey($pcId) -or -not $pcSecurityFilters.ContainsKey($pcId)) { throw 'missing filter' }
    $pcPort = $pcPorts[$pcId]; $pcAddr = $pcAddrs[$pcId]; $pcApp = $pcApps[$pcId]; $pcService = $pcServices[$pcId]
    $pcInterface = $pcInterfaces[$pcId]; $pcType = $pcTypes[$pcId]; $pcSecurity = $pcSecurityFilters[$pcId]
    $pcProfiles = @($pcRule.Profile.ToString().Split(',') | ForEach-Object { $_.Trim() })
    if ($pcProfiles -contains 'Any') { $pcProfiles = @('Domain','Private','Public') }
    $pcUnrestricted = ($pcPort.RemotePort -eq 'Any' -and $pcService.Service -eq 'Any' -and
        $pcInterface.InterfaceAlias -eq 'Any' -and $pcType.InterfaceType -eq 'Any' -and
        $pcSecurity.Authentication -eq 'NotRequired' -and $pcSecurity.Encryption -eq 'NotRequired' -and
        $pcSecurity.LocalUser -eq 'Any' -and $pcSecurity.RemoteUser -eq 'Any' -and
        $pcSecurity.RemoteMachine -eq 'Any' -and $pcSecurity.OverrideBlockRules.ToString() -eq 'False' -and
        ($null -eq $pcApp.Package -or $pcApp.Package -eq 'Any'))
    [ordered]@{profiles=$pcProfiles; protocol=$pcPort.Protocol.ToString(); ports=@($pcPort.LocalPort);
        remote=@($pcAddr.RemoteAddress); local=@($pcAddr.LocalAddress); program=$pcApp.Program.ToString();
        edge=$pcRule.EdgeTraversalPolicy.ToString(); unrestricted=[bool]$pcUnrestricted}
}
$pcAgain = @(Get-NetConnectionProfile -InterfaceIndex $pcIp[0].InterfaceIndex)
if ($pcAgain.Count -ne 1 -or $pcAgain[0].NetworkCategory.ToString() -ne $pcConnections[0].NetworkCategory.ToString()) {
    throw 'profile changed'
}
$pcAgainIp = @(Get-NetIPAddress -IPAddress $pcAddress | Where-Object { $_.AddressState -eq 'Preferred' })
$pcAgainAdapter = @(Get-NetAdapter -InterfaceIndex $pcIp[0].InterfaceIndex)
if ($pcAgainIp.Count -ne 1 -or $pcAgainIp[0].InterfaceIndex -ne $pcIp[0].InterfaceIndex -or
    $pcAgainIp[0].PrefixLength -ne $pcIp[0].PrefixLength -or $pcAgainAdapter.Count -ne 1 -or
    $pcAgainAdapter[0].HardwareInterface -ne $true -or $pcAgainAdapter[0].Status.ToString() -ne 'Up') {
    throw 'interface changed'
}
[ordered]@{interface=[ordered]@{prefix=[int]$pcIp[0].PrefixLength; physical=[bool]$pcAdapter[0].HardwareInterface; category=$pcName};
    profiles=@([ordered]@{name=$pcName; enabled=($pcProfile[0].Enabled.ToString() -eq 'True' -and
    $pcProfile[0].AllowInboundRules.ToString() -eq 'True' -and $pcDisabled.Count -eq 0);
    inbound=$pcProfile[0].DefaultInboundAction.ToString()}); rules=@($pcItems)} | ConvertTo-Json -Depth 6 -Compress
"""
