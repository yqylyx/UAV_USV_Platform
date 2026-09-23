$ErrorActionPreference='Stop'
$repo='C:/Users/hp-pc/Desktop/Project4/p0-acceptance-3e37759'
$localDir='C:/Users/hp-pc/Desktop/Project4/Project/UAV_USV_Platform/.local-tools/p0-integration'
$evidence="$repo/docs/voice-control-p0/integration/evidence/coverage-gaps-20260922"
$state=Get-Content "$localDir/runtime.json" -Raw|ConvertFrom-Json
if($state.workspace -ne $repo){throw 'Workspace mismatch'}
$proc=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.backendPid)"
if(!$proc -or $proc.Name -ne 'java.exe' -or $proc.CommandLine -notlike "*$repo/backend/target/*"){throw 'Backend identity mismatch'}
$before=$state.backendPid
Copy-Item "$localDir/backend.out.log" "$evidence/backend-before-restart.out.log"
Copy-Item "$localDir/backend.err.log" "$evidence/backend-before-restart.err.log"
Stop-Process -Id $before
Wait-Process -Id $before -Timeout 15 -ErrorAction SilentlyContinue
Copy-Item "$localDir/backend.out.log" "$evidence/backend-before-restart.out.log"
Copy-Item "$localDir/backend.err.log" "$evidence/backend-before-restart.err.log"
$s=Get-Content "$localDir/credentials.json" -Raw|ConvertFrom-Json
$env:P0_DB_PASSWORD=$s.dbPassword
$env:P0_ADMIN_PASSWORD=$s.adminPassword
$env:P0_INTEGRATION_TOKEN=$s.integrationToken
$env:P0_PYTHON='D:/soteware/anaconda/python.exe'
$env:P0_RUNNER="$repo/algorithm-service/runner.py"
$configUri=([Uri]"$repo/docs/voice-control-p0/integration/application-p0-integration.yml").AbsoluteUri
$b=Start-Process 'C:/Program Files/Java/jdk-21/bin/java.exe' -ArgumentList @('-jar',"$repo/backend/target/platform-backend-0.1.0-SNAPSHOT.jar","--spring.config.location=$configUri",'--spring.profiles.active=p0-integration','--app.voicecontrol.enabled=true') -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput "$localDir/backend.out.log" -RedirectStandardError "$localDir/backend.err.log"
$state.backendPid=$b.Id
$state.deployedAt=(Get-Date).ToString('o')
$state|ConvertTo-Json|Set-Content "$localDir/runtime.json" -Encoding UTF8
@{oldBackendPid=$before;newBackendPid=$b.Id;at=(Get-Date).ToString('o');jarSha256=(Get-FileHash "$repo/backend/target/platform-backend-0.1.0-SNAPSHOT.jar").Hash}|ConvertTo-Json|Set-Content "$evidence/restart.json" -Encoding UTF8
