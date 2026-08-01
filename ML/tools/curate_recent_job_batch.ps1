param(
    [string]$OutputPath = "ML/data/source/jedi_recent_jobs_100.json",
    [int]$PageCount = 3,
    [int]$JobCount = 100
)

$ErrorActionPreference = "Stop"
$sourceEndpoint = "https://www.arbeitnow.com/api/job-board-api"
$headers = @{ "User-Agent" = "JEDI local ranking-flow fixture curator" }
$generatedAt = [DateTimeOffset]::UtcNow
$cutoff = $generatedAt.AddDays(-7)

function Get-StableHash([string]$Value) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-PlainText([string]$Html) {
    if ([string]::IsNullOrWhiteSpace($Html)) { return "" }
    $withoutTags = [regex]::Replace($Html, "<[^>]+>", " ")
    $decoded = [System.Net.WebUtility]::HtmlDecode($withoutTags)
    return [regex]::Replace($decoded, "\s+", " ").Trim()
}

function Get-RoleFamily([string]$Title) {
    switch -Regex ($Title) {
        "(?i)machine learning|\bml\b|artificial intelligence|\bai\b|data scientist" { return "machine learning" }
        "(?i)data engineer|analytics engineer|business intelligence|\bbi\b|data analyst" { return "data" }
        "(?i)back.?end|api engineer" { return "backend" }
        "(?i)full.?stack" { return "fullstack" }
        "(?i)front.?end|ui engineer" { return "frontend" }
        "(?i)devops|cloud|infrastructure|platform|site reliability|\bsre\b" { return "devops cloud" }
        "(?i)quality assurance|\bqa\b|test automation|test engineer" { return "qa testing" }
        "(?i)security|cyber" { return "security" }
        "(?i)android|ios|mobile" { return "mobile" }
        "(?i)engineer|developer|software|architect|programmer" { return "software engineering" }
        default { return "other" }
    }
}

function Get-Seniority([string]$Title) {
    switch -Regex ($Title) {
        "(?i)intern|working student|werkstudent|graduate|trainee" { return "intern" }
        "(?i)junior|entry.?level|associate" { return "junior" }
        "(?i)principal|staff|lead|head|director|manager|architect|founding" { return "lead" }
        "(?i)senior|\bsr\.?\b" { return "senior" }
        "(?i)mid.?level|\bmid\b" { return "mid" }
        default { return $null }
    }
}

function Get-Skills([string]$Text) {
    $catalog = [ordered]@{
        "Python" = "(?i)\bpython\b"
        "FastAPI" = "(?i)\bfastapi\b"
        "Django" = "(?i)\bdjango\b"
        "Flask" = "(?i)\bflask\b"
        "Java" = "(?i)\bjava\b"
        "Kotlin" = "(?i)\bkotlin\b"
        "Go" = "(?i)\bgolang\b|\bgo developer\b|\bgo engineer\b"
        "Rust" = "(?i)\brust\b"
        "C#" = "(?i)\bc#\b|\.net"
        "C++" = "(?i)c\+\+"
        "JavaScript" = "(?i)\bjavascript\b"
        "TypeScript" = "(?i)\btypescript\b"
        "React" = "(?i)\breact(?:\.js)?\b"
        "Next.js" = "(?i)\bnext\.js\b"
        "Node.js" = "(?i)\bnode(?:\.js)?\b"
        "Ruby on Rails" = "(?i)ruby on rails|\brails\b"
        "PHP" = "(?i)\bphp\b"
        "SQL" = "(?i)\bsql\b"
        "PostgreSQL" = "(?i)\bpostgres(?:ql)?\b"
        "MySQL" = "(?i)\bmysql\b"
        "MongoDB" = "(?i)\bmongodb\b"
        "Redis" = "(?i)\bredis\b"
        "AWS" = "(?i)\baws\b|amazon web services"
        "Azure" = "(?i)\bazure\b"
        "GCP" = "(?i)\bgcp\b|google cloud"
        "Docker" = "(?i)\bdocker\b"
        "Kubernetes" = "(?i)\bkubernetes\b|\bk8s\b"
        "Terraform" = "(?i)\bterraform\b"
        "Machine Learning" = "(?i)machine learning|\bml\b"
        "LLM" = "(?i)large language model|\bllm\b|generative ai"
        "PyTorch" = "(?i)\bpytorch\b"
        "TensorFlow" = "(?i)\btensorflow\b"
        "Spark" = "(?i)\bspark\b"
        "Kafka" = "(?i)\bkafka\b"
        "GraphQL" = "(?i)\bgraphql\b"
        "REST APIs" = "(?i)rest(?:ful)? api|\bapi design\b"
        "Git" = "(?i)\bgit\b|github|gitlab"
    }
    $found = foreach ($entry in $catalog.GetEnumerator()) {
        if ($Text -match $entry.Value) { $entry.Key }
    }
    return @($found | Select-Object -First 16)
}

function Get-TechnologyScore([string]$Title, [bool]$Remote) {
    $score = 0
    if ($Title -match "(?i)machine learning|data scientist|data engineer|back.?end|full.?stack|software engineer|python|artificial intelligence|\bai\b") { $score += 100 }
    elseif ($Title -match "(?i)engineer|developer|software|data|front.?end|devops|cloud|platform|site reliability|\bsre\b|quality assurance|\bqa\b|database|security|architect|programmer|analytics|technical|android|ios|mobile|automation") { $score += 60 }
    if ($Remote) { $score += 5 }
    return $score
}

$rawJobs = @()
foreach ($page in 1..$PageCount) {
    $response = Invoke-RestMethod -Uri "${sourceEndpoint}?page=$page" -Headers $headers
    $rawJobs += @($response.data)
}

$seenUrls = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$seenJobs = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$candidates = foreach ($raw in ($rawJobs | Sort-Object created_at -Descending)) {
    $postedAt = [DateTimeOffset]::FromUnixTimeSeconds([int64]$raw.created_at)
    if ($postedAt -lt $cutoff) { continue }
    $identity = "$($raw.company_name)|$($raw.title)|$($raw.location)"
    if (-not $seenUrls.Add([string]$raw.url) -or -not $seenJobs.Add($identity)) { continue }
    $plainText = Get-PlainText ([string]$raw.description)
    $searchText = "$($raw.title) $plainText"
    $skills = @(Get-Skills $searchText)
    $workMode = if ([bool]$raw.remote) { "remote" } else { "onsite_or_hybrid" }
    $employmentType = if (@($raw.job_types).Count) { (@($raw.job_types) -join ", ") } else { $null }
    $skillSummary = if ($skills.Count) { $skills -join ", " } else { "No explicit technology keywords detected" }
    $location = if ([string]::IsNullOrWhiteSpace([string]$raw.location)) { "Unspecified" } else { [string]$raw.location }
    $description = "$($raw.title) role at $($raw.company_name). Listed for $location with $workMode working conditions. Detected technologies or focus areas: $skillSummary. Review the source listing for complete responsibilities and eligibility requirements."
    [pscustomobject]@{
        score = Get-TechnologyScore ([string]$raw.title) ([bool]$raw.remote)
        shuffleKey = Get-StableHash "$($raw.slug)|$($generatedAt.ToString('yyyy-MM-dd'))"
        job = [ordered]@{
            companyName = [string]$raw.company_name
            roleTitle = [string]$raw.title
            description = $description
            applyUrl = [string]$raw.url
            roleFamily = Get-RoleFamily ([string]$raw.title)
            seniority = Get-Seniority ([string]$raw.title)
            location = $location
            workMode = $workMode
            employmentType = $employmentType
            skills = @($skills)
            experienceMinYears = $null
            experienceMaxYears = $null
            salaryMin = $null
            salaryMax = $null
            salaryCurrency = $null
            postedAt = $postedAt.ToUniversalTime().ToString("o")
            applicationDeadline = $null
            canApplyNow = $true
        }
    }
}

$technical = @(
    $candidates |
        Where-Object { $_.score -gt 0 } |
        Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "shuffleKey"; Ascending = $true } |
        Select-Object -First 80
)
$controlsNeeded = $JobCount - $technical.Count
$controls = @($candidates | Where-Object { $_.score -eq 0 } | Sort-Object shuffleKey | Select-Object -First $controlsNeeded)
$selected = @($technical + $controls)
if ($selected.Count -ne $JobCount) {
    throw "Only $($selected.Count) unique jobs were available; expected $JobCount. Increase PageCount or relax the selection."
}

$jobs = @($selected | Sort-Object shuffleKey | ForEach-Object { $_.job })
$envelope = [ordered]@{
    externalBatchId = "online-recent-jobs-$($generatedAt.ToString('yyyyMMdd-HHmmss'))-100-v1"
    schemaVersion = "import-v1"
    promptVersion = "arbeitnow-public-api-curation-v1"
    generatedAt = $generatedAt.ToUniversalTime().ToString("o")
    jobs = $jobs
}

$resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$outputDirectory = Split-Path -Parent $resolvedOutput
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$json = $envelope | ConvertTo-Json -Depth 8 -Compress
[System.IO.File]::WriteAllText($resolvedOutput, $json, [System.Text.UTF8Encoding]::new($false))

[pscustomobject]@{
    outputPath = $resolvedOutput
    jobs = $jobs.Count
    technicalRoles = $technical.Count
    controlRoles = $controls.Count
    newestPosting = ($jobs.postedAt | Sort-Object -Descending | Select-Object -First 1)
    oldestPosting = ($jobs.postedAt | Sort-Object | Select-Object -First 1)
    source = $sourceEndpoint
} | ConvertTo-Json
