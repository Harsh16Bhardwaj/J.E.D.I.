param(
  [string]$InputCsv = "D:\ML\JEDI\jedi-annotated-2026-06-27_completed.csv",
  [string]$OutputCsv = "D:\ML\JEDI\jedi-annotated-2026-06-27_prepared.csv"
)

$ErrorActionPreference = "Stop"

function Is-Missing($value) {
  return $null -eq $value -or [string]::IsNullOrWhiteSpace([string]$value)
}

function Norm([string]$value) {
  if (Is-Missing $value) { return "" }
  return ([regex]::Replace($value.ToLowerInvariant().Trim(), "\s+", " "))
}

function Json-Array($items) {
  $clean = @($items | Where-Object { -not (Is-Missing $_) } | ForEach-Object { Norm $_ } | Select-Object -Unique)
  return ($clean | ConvertTo-Json -Compress)
}

function Has-Any([string]$text, [string[]]$patterns) {
  foreach ($pattern in $patterns) {
    if ($text -match $pattern) { return $true }
  }
  return $false
}

function Get-RoleFamilyStandard($row) {
  $roleText = Norm("$($row.role_title) $($row.role_family)")
  $skillText = Norm("$($row.skills_or_requirements)")
  if (Has-Any $roleText @("qa", "quality assurance", "test engineer", "automation testing")) { return "qa_testing" }
  if (Has-Any $roleText @("full[ -]?stack", "fullstack")) { return "fullstack" }
  if (Has-Any $roleText @("front[ -]?end", "frontend", "ui engineer", "mobile")) { return "frontend" }
  if (Has-Any $roleText @("back[ -]?end", "backend", "api", "server")) { return "backend" }
  if (Has-Any $roleText @("data engineer", "etl", "pipeline", "spark", "airflow", "warehouse")) { return "data_engineering" }
  if (Has-Any $roleText @("data scientist", "data science", "scientist")) { return "data_science" }
  if (Has-Any $roleText @("analytics", "analyst", "business intelligence", "\bbi\b")) { return "analytics" }
  if (Has-Any $roleText @("devops", "sre", "site reliability", "platform engineer", "infrastructure")) { return "devops_cloud" }
  if (Has-Any $roleText @("machine learning", "\bml\b", "\bai engineer", "ai engineering", "llm engineer", "rag engineer", "generative ai", "agentic ai", "computer vision", "nlp")) { return "ml_ai" }
  if (Has-Any $roleText @("product engineer", "product engineering")) { return "product_engineering" }
  if (Has-Any $roleText @("software engineer", "sde", "associate software")) { return "backend" }
  if (Has-Any $skillText @("react", "angular", "vue")) { return "frontend" }
  if (Has-Any $skillText @("java", "spring", "node", "django", "fastapi", "rest api", "microservices")) { return "backend" }
  if (Has-Any $skillText @("kubernetes", "docker", "ci/cd", "cloud platforms")) { return "devops_cloud" }
  if (Has-Any $skillText @("machine learning", "llms", "rag", "model evaluation")) { return "ml_ai" }
  return "other"
}

function Get-SeniorityStandard($row) {
  $text = Norm("$($row.seniority) $($row.role_title)")
  $exp = $null
  if (-not (Is-Missing $row.experience_min_years)) {
    [double]::TryParse([string]$row.experience_min_years, [ref]$exp) | Out-Null
  }
  if (Has-Any $text @("principal", "architect")) { return "principal" }
  if (Has-Any $text @("\bstaff\b")) { return "staff" }
  if (Has-Any $text @("\blead\b", "manager")) { return "lead" }
  if (Has-Any $text @("senior", "sr\.", "senior-heavy")) { return "senior" }
  if (Has-Any $text @("mid/senior", "mid /", "early-mid", "junior/mid")) { return "early_mid" }
  if (Has-Any $text @("\bmid\b", "sde ii", "3\+ years")) { return "mid" }
  if (Has-Any $text @("internship", "\bintern\b", "student")) { return "intern" }
  if (Has-Any $text @("new grad", "graduate", "campus")) { return "new_grad" }
  if (Has-Any $text @("entry", "entry_level", "0-2", "0 to 2", "sde i", "software engineer i", "associate")) { return "entry_level" }
  if (Has-Any $text @("junior", "\bjr\b")) { return "junior" }
  if ($exp -ne $null) {
    if ($exp -le 0) { return "entry_level" }
    if ($exp -le 1) { return "junior" }
    if ($exp -le 2) { return "early_mid" }
    if ($exp -le 4) { return "mid" }
    return "senior"
  }
  return "unknown"
}

function Get-EmploymentTypeStandard($row) {
  $text = Norm("$($row.employment_type) $($row.role_title)")
  if (Has-Any $text @("internship", "\bintern\b")) { return "internship" }
  if (Has-Any $text @("accelerator", "apprentice", "trainee")) { return "apprenticeship" }
  if (Has-Any $text @("freelance")) { return "freelance" }
  if (Has-Any $text @("part[ -]?time")) { return "part_time" }
  if (Has-Any $text @("contract")) { return "contract" }
  if (Has-Any $text @("temporary", "temp")) { return "temporary" }
  if (Has-Any $text @("full[ -]?time", "full_time", "permanent", "employee")) { return "full_time" }
  return "unknown"
}

function Get-WorkModeStandard($row) {
  $text = Norm("$($row.work_mode) $($row.location) $($row.employment_type)")
  if (Has-Any $text @("onsite or remote", "on[- ]?site or remote", "office or remote", "flexible")) { return "flexible" }
  if (Has-Any $text @("hybrid")) { return "hybrid" }
  if (Has-Any $text @("remote only", "\bremote\b", "work from home")) { return "remote" }
  if (Has-Any $text @("in office", "onsite", "on-site", "office")) { return "onsite" }
  return "unknown"
}

function Get-LocationInfo($row) {
  $text = Norm("$($row.location)")
  $city = "unknown"
  $country = "unknown"
  $bucket = "unknown"

  $isBengaluru = Has-Any $text @("bengaluru", "bangalore")
  $isNcr = Has-Any $text @("gurgaon", "gurugram", "noida", "delhi", "new delhi", "faridabad", "\bncr\b")
  $isIndia = Has-Any $text @("india", "bengaluru", "bangalore", "gurgaon", "gurugram", "noida", "delhi", "faridabad", "hyderabad", "pune", "mumbai", "chennai", "karnataka", "haryana", "telangana", "maharashtra", "tamil nadu")

  if ($isBengaluru) { $city = "bengaluru"; $bucket = "bengaluru"; $country = "india" }
  elseif ($isNcr) { $city = "delhi_ncr"; $bucket = "delhi_ncr"; $country = "india" }
  elseif (Has-Any $text @("hyderabad")) { $city = "hyderabad"; $bucket = "hyderabad"; $country = "india" }
  elseif (Has-Any $text @("pune")) { $city = "pune"; $bucket = "pune"; $country = "india" }
  elseif (Has-Any $text @("mumbai")) { $city = "mumbai"; $bucket = "mumbai"; $country = "india" }
  elseif (Has-Any $text @("chennai")) { $city = "chennai"; $bucket = "chennai"; $country = "india" }
  elseif (Has-Any $text @("san francisco", "new york", "united states", "\busa\b", "mountain view", "california", "\bca\b", "\bny\b", "austin", "boston", "seattle")) { $country = "us"; $bucket = "us" }
  elseif (Has-Any $text @("london", "germany", "netherlands", "france", "europe", "uk", "united kingdom")) { $country = "europe"; $bucket = "europe" }
  elseif ($isIndia) { $country = "india"; $bucket = "india_other" }

  if ((Get-WorkModeStandard $row) -eq "remote") {
    if ($isIndia) { $bucket = "india_remote"; if ($country -eq "unknown") { $country = "india" } }
    elseif (Has-Any $text @("everywhere", "worldwide", "global", "anywhere")) { $bucket = "global_remote" }
  }

  return [pscustomobject]@{
    city_standard = $city
    country_standard = $country
    location_bucket = $bucket
    is_bengaluru = [bool]$isBengaluru
    is_gurgaon_ncr = [bool]$isNcr
    is_india = [bool]$isIndia
  }
}

function Get-ExperienceBucket($value) {
  if (Is-Missing $value) { return "unknown" }
  $n = 0.0
  if (-not [double]::TryParse([string]$value, [ref]$n)) { return "unknown" }
  if ($n -le 0) { return "0" }
  if ($n -le 1) { return "1" }
  if ($n -le 2) { return "2" }
  if ($n -le 3) { return "3" }
  return "4_plus"
}

function Get-SalaryMidpoint($minValue, $maxValue) {
  $hasMin = -not (Is-Missing $minValue)
  $hasMax = -not (Is-Missing $maxValue)
  if (-not $hasMin -and -not $hasMax) { return "" }
  $min = 0.0
  $max = 0.0
  if ($hasMin -and -not [double]::TryParse([string]$minValue, [ref]$min)) { $hasMin = $false }
  if ($hasMax -and -not [double]::TryParse([string]$maxValue, [ref]$max)) { $hasMax = $false }
  if ($hasMin -and $hasMax) { return [math]::Round(($min + $max) / 2, 2) }
  if ($hasMin) { return $min }
  return $max
}

function Normalize-SkillToken([string]$token) {
  $t = Norm $token
  if ($t -eq "") { return "" }
  $map = @{
    "js" = "javascript"; "node" = "node.js"; "nodejs" = "node.js"; "reactjs" = "react";
    "postgresql" = "postgresql"; "postgres" = "postgresql"; "mysql" = "mysql";
    "rest api" = "rest apis"; "rest apis" = "rest apis"; "api" = "apis"; "apis" = "apis";
    "ml" = "machine learning"; "ai" = "artificial intelligence"; "llm" = "llms"; "llms" = "llms";
    "gen ai" = "generative ai"; "genai" = "generative ai";
    "k8s" = "kubernetes"; "ci cd" = "ci/cd"; "cicd" = "ci/cd";
  }
  if ($map.ContainsKey($t)) { return $map[$t] }
  return $t
}

function Parse-Skills([string]$skillText) {
  if (Is-Missing $skillText) { return @() }
  $parts = [regex]::Split($skillText, ";|,|\||`n|`r")
  $tokens = New-Object System.Collections.Generic.List[string]
  foreach ($part in $parts) {
    $clean = Normalize-SkillToken $part
    if ($clean.Length -lt 2) { continue }
    $tokens.Add($clean)
  }
  return @($tokens | Select-Object -Unique)
}

function Get-CompanyDomainSkills($row) {
  $text = Norm("$($row.company_name) $($row.role_title) $($row.role_family)")
  $skills = New-Object System.Collections.Generic.List[string]

  if (Has-Any $text @("cloudsek", "security", "secure", "cyber", "patronus")) {
    @("security fundamentals", "threat modeling", "secure coding") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("mistral", "netomi", "oliv ai", "autodraft", "mirian", "voice", "agent", "llm", "ai")) {
    @("llms", "prompt engineering", "ai product integration") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("openvector", "vector", "rag", "search")) {
    @("vector search", "embeddings", "retrieval systems") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("biotech", "health", "healthcare", "whoop", "miro biotech")) {
    @("healthcare data", "privacy awareness", "regulated product workflows") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("binance", "crypto", "web3", "blockchain")) {
    @("web3 fundamentals", "financial systems", "security awareness") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("greenchoice", "climate", "sustainability")) {
    @("sustainability data", "analytics workflows", "product metrics") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("aviate", "travel")) {
    @("travel product workflows", "booking systems", "user-facing systems") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("adtech", "marketing", "crm", "sales", "oliv")) {
    @("crm workflows", "sales automation", "product analytics") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("anaplan", "planning", "finance", "fintech", "investing")) {
    @("business planning systems", "financial data", "enterprise workflows") | ForEach-Object { $skills.Add($_) }
  }
  if (Has-Any $text @("nirmata", "kubernetes", "cloud", "platform")) {
    @("cloud native systems", "kubernetes", "platform reliability") | ForEach-Object { $skills.Add($_) }
  }

  return @($skills | ForEach-Object { Normalize-SkillToken $_ } | Select-Object -Unique)
}

function Get-FallbackSkills($row, [string]$roleStandard, [string]$seniorityStandard) {
  $skills = New-Object System.Collections.Generic.List[string]
  switch ($roleStandard) {
    "backend" {
      @("backend fundamentals", "rest apis", "databases", "sql", "git", "debugging") | ForEach-Object { $skills.Add($_) }
    }
    "frontend" {
      @("html", "css", "javascript", "react", "responsive ui", "git", "browser debugging") | ForEach-Object { $skills.Add($_) }
    }
    "fullstack" {
      @("javascript", "react", "node.js", "rest apis", "databases", "git", "deployment basics") | ForEach-Object { $skills.Add($_) }
    }
    "ml_ai" {
      @("python", "machine learning", "llms", "prompting", "rag", "data preprocessing", "model evaluation") | ForEach-Object { $skills.Add($_) }
    }
    "data_engineering" {
      @("python", "sql", "etl", "data pipelines", "data modeling", "cloud basics", "workflow orchestration") | ForEach-Object { $skills.Add($_) }
    }
    "data_science" {
      @("python", "pandas", "statistics", "machine learning", "model evaluation", "data visualization") | ForEach-Object { $skills.Add($_) }
    }
    "devops_cloud" {
      @("linux", "docker", "kubernetes", "cloud platforms", "ci/cd", "monitoring", "scripting") | ForEach-Object { $skills.Add($_) }
    }
    "analytics" {
      @("sql", "excel", "dashboards", "business metrics", "data visualization", "communication") | ForEach-Object { $skills.Add($_) }
    }
    "qa_testing" {
      @("test cases", "manual testing", "automation testing", "bug reporting", "api testing", "regression testing") | ForEach-Object { $skills.Add($_) }
    }
    "product_engineering" {
      @("product thinking", "fullstack development", "apis", "databases", "user workflows", "rapid prototyping") | ForEach-Object { $skills.Add($_) }
    }
    default {
      @("software engineering fundamentals", "problem solving", "git", "debugging", "communication") | ForEach-Object { $skills.Add($_) }
    }
  }

  $title = Norm $row.role_title
  if (Has-Any $title @("python")) { $skills.Add("python") }
  if (Has-Any $title @("java")) { $skills.Add("java") }
  if (Has-Any $title @("react")) { $skills.Add("react") }
  if (Has-Any $title @("node")) { $skills.Add("node.js") }
  if (Has-Any $title @("security", "cyber")) { $skills.Add("security fundamentals") }
  if (Has-Any $title @("voice", "agent", "llm", "ai")) { $skills.Add("llms"); $skills.Add("agentic ai") }
  if (Has-Any $title @("data")) { $skills.Add("sql"); $skills.Add("data pipelines") }
  Get-CompanyDomainSkills $row | ForEach-Object { $skills.Add($_) }

  switch ($seniorityStandard) {
    "intern" { $skills.Add("learning mindset"); $skills.Add("basic dsa") }
    "new_grad" { $skills.Add("dsa"); $skills.Add("cs fundamentals") }
    "entry_level" { $skills.Add("cs fundamentals"); $skills.Add("ownership") }
    "junior" { $skills.Add("code quality"); $skills.Add("team collaboration") }
    "early_mid" { $skills.Add("feature ownership"); $skills.Add("system design basics") }
    "mid" { $skills.Add("system design"); $skills.Add("production ownership") }
    "senior" { $skills.Add("architecture"); $skills.Add("mentoring") }
    "lead" { $skills.Add("technical leadership"); $skills.Add("cross-functional planning") }
    "staff" { $skills.Add("technical strategy"); $skills.Add("architecture") }
    "principal" { $skills.Add("architecture"); $skills.Add("organization-level technical direction") }
  }

  return @($skills | ForEach-Object { Normalize-SkillToken $_ } | Select-Object -Unique)
}

function Standardize-Key([string]$value) {
  $x = Norm $value
  $x = [regex]::Replace($x, "[^a-z0-9]+", "_").Trim("_")
  return $x
}

$rows = Import-Csv -LiteralPath $InputCsv
$prepared = @()

foreach ($row in $rows) {
  $roleStandard = Get-RoleFamilyStandard $row
  $seniorityStandard = Get-SeniorityStandard $row
  $employmentStandard = Get-EmploymentTypeStandard $row
  $workModeStandard = Get-WorkModeStandard $row
  $loc = Get-LocationInfo $row
  $originalSkills = [string]$row.skills_or_requirements
  $hadSkills = -not (Is-Missing $originalSkills)

  if ($hadSkills) {
    $skills = Parse-Skills $originalSkills
    $skillText = $originalSkills
    $imputationType = "original"
  } else {
    $skills = Get-FallbackSkills $row $roleStandard $seniorityStandard
    $skillText = ($skills -join "; ")
    $imputationType = "role_based_fallback"
  }

  $salaryMidpoint = Get-SalaryMidpoint $row.salary_min $row.salary_max
  $salaryAvailable = -not (Is-Missing $salaryMidpoint)
  $nearDuplicateKey = "{0}|{1}|{2}" -f (Standardize-Key $row.company_name), (Standardize-Key $row.role_title), $loc.location_bucket

  $row | Add-Member -NotePropertyName "skills_or_requirements_original" -NotePropertyValue $originalSkills -Force
  $row.skills_or_requirements = $skillText
  $row | Add-Member -NotePropertyName "skills_array" -NotePropertyValue (Json-Array $skills) -Force
  $row | Add-Member -NotePropertyName "has_skills_or_requirements" -NotePropertyValue ([bool]$hadSkills) -Force
  $row | Add-Member -NotePropertyName "skills_imputation_type" -NotePropertyValue $imputationType -Force
  $row | Add-Member -NotePropertyName "role_family_standard" -NotePropertyValue $roleStandard -Force
  $row | Add-Member -NotePropertyName "seniority_standard" -NotePropertyValue $seniorityStandard -Force
  $row | Add-Member -NotePropertyName "employment_type_standard" -NotePropertyValue $employmentStandard -Force
  $row | Add-Member -NotePropertyName "work_mode_standard" -NotePropertyValue $workModeStandard -Force
  $row | Add-Member -NotePropertyName "city_standard" -NotePropertyValue $loc.city_standard -Force
  $row | Add-Member -NotePropertyName "country_standard" -NotePropertyValue $loc.country_standard -Force
  $row | Add-Member -NotePropertyName "location_bucket" -NotePropertyValue $loc.location_bucket -Force
  $row | Add-Member -NotePropertyName "is_bengaluru" -NotePropertyValue $loc.is_bengaluru -Force
  $row | Add-Member -NotePropertyName "is_gurgaon_ncr" -NotePropertyValue $loc.is_gurgaon_ncr -Force
  $row | Add-Member -NotePropertyName "is_india" -NotePropertyValue $loc.is_india -Force
  $row | Add-Member -NotePropertyName "experience_min_bucket" -NotePropertyValue (Get-ExperienceBucket $row.experience_min_years) -Force
  $row | Add-Member -NotePropertyName "salary_midpoint" -NotePropertyValue $salaryMidpoint -Force
  $row | Add-Member -NotePropertyName "salary_available" -NotePropertyValue ([bool]$salaryAvailable) -Force
  $row | Add-Member -NotePropertyName "near_duplicate_key" -NotePropertyValue $nearDuplicateKey -Force
  $row | Add-Member -NotePropertyName "company_name_standard" -NotePropertyValue (Standardize-Key $row.company_name) -Force
  $row | Add-Member -NotePropertyName "role_title_standard" -NotePropertyValue (Standardize-Key $row.role_title) -Force

  $prepared += $row
}

$prepared | Export-Csv -LiteralPath $OutputCsv -NoTypeInformation -Encoding UTF8

$summary = [pscustomobject]@{
  input_rows = $rows.Count
  output_rows = $prepared.Count
  output_csv = $OutputCsv
  fallback_skill_rows = @($prepared | Where-Object { $_.skills_imputation_type -eq "role_based_fallback" }).Count
  role_family_standard_values = (($prepared | Group-Object role_family_standard | Sort-Object Count -Descending | ForEach-Object { "$($_.Name):$($_.Count)" }) -join ", ")
  seniority_standard_values = (($prepared | Group-Object seniority_standard | Sort-Object Count -Descending | ForEach-Object { "$($_.Name):$($_.Count)" }) -join ", ")
}

$summary
