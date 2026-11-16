$ErrorActionPreference = "Stop"

$env:AWS_PROFILE = "anoop-admin"
$env:AWS_DEFAULT_REGION = "ap-south-1"
$env:TF_VAR_aws_region = "ap-south-1"

$EC2_SG_ID = "sg-07c0c45aa05193615"
$RDS_SG_ID = "sg-048083776d9b6efbe"
$KEY_PATH = "D:\test-key-july.pem"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Command"
    }
}

function Get-AwsJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $result = & aws @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI command failed."
    }

    return ($result | ConvertFrom-Json)
}

function Get-TerraformOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $result = & terraform output -raw $Name

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read Terraform output: $Name"
    }

    return $result.Trim()
}

$PLAN_FILE = "deployment.tfplan"

try {

    # 1. CHECK REQUIRED SOFTWARE

    Write-Host "`n[1/10] Checking required software..."

    foreach ($tool in @("aws", "terraform")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "$tool is not installed or not available in PATH."
        }
    }

    Write-Host "AWS CLI and Terraform are installed."

    # 2. VERIFY AWS AUTHENTICATION

    Write-Host "`n[2/10] Verifying AWS identity..."

    $identity = Get-AwsJson -Arguments @(
        "sts",
        "get-caller-identity"
    )

    Write-Host "Account: $($identity.Account)"
    Write-Host "User: $($identity.Arn)"

    if ($identity.Account -ne "479537131023") {
        throw "Unexpected AWS account. Stopping deployment."
    }

    # 3. VERIFY EXISTING AWS RESOURCES

    Write-Host "`n[3/10] Verifying existing AWS resources..."

    Get-AwsJson -Arguments @(
        "ec2",
        "describe-vpcs",
        "--vpc-ids",
        "vpc-0634159ca6c52888a"
    ) | Out-Null

    Get-AwsJson -Arguments @(
        "ec2",
        "describe-subnets",
        "--subnet-ids",
        "subnet-052617036c499d968"
    ) | Out-Null

    Get-AwsJson -Arguments @(
        "ec2",
        "describe-security-groups",
        "--group-ids",
        $EC2_SG_ID,
        $RDS_SG_ID
    ) | Out-Null

    Get-AwsJson -Arguments @(
        "ec2",
        "describe-key-pairs",
        "--key-names",
        "test-key-july"
    ) | Out-Null

    Get-AwsJson -Arguments @(
        "iam",
        "get-instance-profile",
        "--instance-profile-name",
        "InventoryAppEC2Role"
    ) | Out-Null

    Get-AwsJson -Arguments @(
        "ecr",
        "describe-repositories",
        "--repository-names",
        "inventory-management-system"
    ) | Out-Null

    Write-Host "Existing AWS resources verified."

    # 4. CHECK SSH PRIVATE KEY

    Write-Host "`n[4/10] Checking SSH private key..."

    if (-not (Test-Path $KEY_PATH)) {
        throw "SSH private key not found: $KEY_PATH"
    }

    Write-Host "SSH private key found."

    # 5. DETECT PUBLIC IP

    Write-Host "`n[5/10] Detecting current public IP..."

    $PUBLIC_IP = $null

    $ipServices = @(
        "https://checkip.amazonaws.com",
        "https://api.ipify.org",
        "https://ifconfig.me/ip"
    )

    foreach ($service in $ipServices) {
        try {
            $response = Invoke-RestMethod -Uri $service -TimeoutSec 10

            $parsedIP = $null

            if (
                [System.Net.IPAddress]::TryParse(
                    "$response".Trim(),
                    [ref]$parsedIP
                ) -and
                $parsedIP.AddressFamily -eq
                [System.Net.Sockets.AddressFamily]::InterNetwork
            ) {
                $PUBLIC_IP = $parsedIP.ToString()
                break
            }
        }
        catch {
            Write-Host "Could not retrieve IP from $service"
        }
    }

    if (-not $PUBLIC_IP) {
        throw "Unable to detect public IPv4 address."
    }

    $CURRENT_CIDR = "$PUBLIC_IP/32"

    Write-Host "Detected public IP: $PUBLIC_IP"

    # 6. UPDATE EC2 SSH RULE


    # 6. UPDATE EC2 SSH RULE

    Write-Host "`n[6/10] Updating EC2 SSH access..."

    $ec2Rules = Get-AwsJson -Arguments @(
        "ec2",
        "describe-security-group-rules",
        "--filters",
        "Name=group-id,Values=$EC2_SG_ID"
    )

    $sshRules = @(
        $ec2Rules.SecurityGroupRules | Where-Object {
            $_.IsEgress -eq $false -and
            $_.IpProtocol -eq "tcp" -and
            $_.FromPort -eq 22 -and
            $_.ToPort -eq 22 -and
            -not [string]::IsNullOrWhiteSpace($_.CidrIpv4) -and
            $_.Description -ne "Temporary-GitHub-Actions-SSH"
        }
    )

    if ($sshRules.Count -gt 1) {
        throw "Multiple eligible IPv4 SSH rules found. Review the security group manually before updating."
    }

    if ($sshRules.Count -eq 1) {

        $existingRule = $sshRules[0]

        if ($existingRule.CidrIpv4 -eq $CURRENT_CIDR) {
            Write-Host "SSH rule already uses current IP: $CURRENT_CIDR"
        }
        else {

            Write-Host "Updating existing SSH rule..."
            Write-Host "Old IP: $($existingRule.CidrIpv4)"
            Write-Host "New IP: $CURRENT_CIDR"

            $ruleUpdate = @(
                @{
                    SecurityGroupRuleId = $existingRule.SecurityGroupRuleId
                    SecurityGroupRule = @{
                        IpProtocol  = "tcp"
                        FromPort    = 22
                        ToPort      = 22
                        CidrIpv4    = $CURRENT_CIDR
                        Description = "Terraform-Managed-SSH"
                    }
                }
            )

            $ruleJson = ConvertTo-Json -InputObject $ruleUpdate -Depth 5 -Compress

            # Write JSON to a temp file (UTF-8 without BOM) to avoid
            # PowerShell stripping double quotes when calling aws.
            $ruleFile = Join-Path ([System.IO.Path]::GetTempPath()) "sg-rule-update.json"
            [System.IO.File]::WriteAllText(
                $ruleFile,
                $ruleJson,
                (New-Object System.Text.UTF8Encoding($false))
            )

            try {
                Invoke-Checked -Command "aws" -Arguments @(
                    "ec2",
                    "modify-security-group-rules",
                    "--group-id",
                    $EC2_SG_ID,
                    "--security-group-rules",
                    "file://$ruleFile"
                )
            }
            finally {
                Remove-Item $ruleFile -Force -ErrorAction SilentlyContinue
            }

            Write-Host "SSH rule updated successfully."
        }
    }
    else {

        Write-Host "No existing eligible IPv4 SSH rule found. Creating one..."

        Invoke-Checked -Command "aws" -Arguments @(
            "ec2",
            "authorize-security-group-ingress",
            "--group-id",
            $EC2_SG_ID,
            "--protocol",
            "tcp",
            "--port",
            "22",
            "--cidr",
            $CURRENT_CIDR,
            "--description",
            "Terraform-Managed-SSH"
        )

        Write-Host "New SSH rule created successfully."
    }

    # 7. VERIFY RDS MYSQL RULE

    Write-Host "`n[7/10] Checking RDS MySQL access..."

    $rdsSG = Get-AwsJson -Arguments @(
        "ec2",
        "describe-security-groups",
        "--group-ids",
        $RDS_SG_ID
    )

    $mysqlRuleExists = $false

    foreach ($permission in $rdsSG.SecurityGroups[0].IpPermissions) {

        if ($permission.IpProtocol -eq "tcp" -and
            $permission.FromPort -eq 3306 -and
            $permission.ToPort -eq 3306) {

            foreach ($pair in $permission.UserIdGroupPairs) {
                if ($pair.GroupId -eq $EC2_SG_ID) {
                    $mysqlRuleExists = $true
                }
            }
        }
    }

    if (-not $mysqlRuleExists) {

        Write-Host "Adding MySQL access from EC2 security group."

        Invoke-Checked -Command "aws" -Arguments @(
            "ec2",
            "authorize-security-group-ingress",
            "--group-id",
            $RDS_SG_ID,
            "--protocol",
            "tcp",
            "--port",
            "3306",
            "--source-group",
            $EC2_SG_ID
        )
    }
    else {
        Write-Host "RDS MySQL rule already exists."
    }

    # 8. VERIFY RDS SUBNETS

    Write-Host "`n[8/10] Checking RDS subnet availability..."

    $subnets = Get-AwsJson -Arguments @(
        "ec2",
        "describe-subnets",
        "--filters",
        "Name=vpc-id,Values=vpc-0634159ca6c52888a"
    )

    $availabilityZones = @(
        $subnets.Subnets |
        Select-Object -ExpandProperty AvailabilityZone -Unique
    )

    if ($availabilityZones.Count -lt 2) {
        throw "RDS requires subnets in at least two Availability Zones."
    }

    Write-Host "Available AZs: $($availabilityZones -join ', ')"

    # 9. GET DATABASE PASSWORD

    Write-Host "`n[9/10] Enter RDS master password..."

    $securePassword = Read-Host "Enter RDS password" -AsSecureString

    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $securePassword
    )

    try {
        $DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
            $passwordPointer
        )
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }

    if ($DB_PASSWORD.Length -lt 8 -or $DB_PASSWORD.Length -gt 41) {
        throw "Password must contain between 8 and 41 characters."
    }

    if ($DB_PASSWORD -match '[\s/@"]') {
        throw 'Password cannot contain whitespace, /, @, or ".'
    }

    $env:TF_VAR_db_password = $DB_PASSWORD

    # 10. TERRAFORM EXECUTION

    Write-Host "`n[10/10] Running Terraform..."

    Invoke-Checked -Command "terraform" -Arguments @("init")

    Invoke-Checked -Command "terraform" -Arguments @("fmt", "-check")

    Invoke-Checked -Command "terraform" -Arguments @("validate")

    Write-Host "`nCreating Terraform plan..."

    Invoke-Checked -Command "terraform" -Arguments @(
        "plan",
        "-out=$PLAN_FILE"
    )

    Write-Host "`nReview the plan carefully."

    $confirmation = Read-Host "Type APPLY to create AWS resources"

    if ($confirmation -cne "APPLY") {
        Write-Host "Deployment cancelled. No Terraform apply was performed."
        exit
    }

    Write-Host "`nApplying Terraform plan..."

    Invoke-Checked -Command "terraform" -Arguments @(
        "apply",
        $PLAN_FILE
    )

    # WAIT FOR RDS

    Write-Host "`nWaiting for RDS to become available..."

    $dbIdentifier = Get-TerraformOutput -Name "rds_identifier"

    Invoke-Checked -Command "aws" -Arguments @(
        "rds",
        "wait",
        "db-instance-available",
        "--db-instance-identifier",
        $dbIdentifier
    )

    # DISPLAY OUTPUTS

    Write-Host "`nDeployment completed."

    $outputNames = @(
        "ec2_instance_id",
        "ec2_public_ip",
        "ec2_public_dns",
        "ec2_security_group_id",
        "rds_identifier",
        "rds_endpoint",
        "rds_port",
        "rds_database_name",
        "rds_security_group_id",
        "ecr_repository_uri",
        "iam_instance_profile"
    )

    $outputLines = @()

    foreach ($name in $outputNames) {

        $value = Get-TerraformOutput -Name $name

        $line = "$name = $value"

        Write-Host $line

        $outputLines += $line
    }

    $sshIP = Get-TerraformOutput -Name "ec2_public_ip"

    $outputLines += "SSH command = ssh -i `"$KEY_PATH`" ec2-user@$sshIP"

    $outputLines | Set-Content -Path "deployment-outputs.txt"

    Write-Host "`nOutputs saved to deployment-outputs.txt"

    Write-Host "`nSSH command:"
    Write-Host "ssh -i `"$KEY_PATH`" ec2-user@$sshIP"

}
finally {

    Remove-Item Env:\TF_VAR_db_password -ErrorAction SilentlyContinue

    $DB_PASSWORD = $null

    if (Test-Path $PLAN_FILE) {
        Remove-Item $PLAN_FILE -Force
    }
}