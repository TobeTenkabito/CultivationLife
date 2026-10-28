# Mechanical grid packing only. All water silhouettes come from the painted source.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskSource = Join-Path $taskRoot 'design/tide-water-20261028/water-keyframes.png'
$taskTarget = Join-Path $taskRoot 'web/assets/pixel/tide/water-keyframes.png'
$taskImage = [System.Drawing.Bitmap]::new($taskSource)
$taskAtlas = [System.Drawing.Bitmap]::new(1536,1152,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$taskGraphics = [System.Drawing.Graphics]::FromImage($taskAtlas)
try {
    $taskGraphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
    $taskGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $taskGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
    for ($frame = 0; $frame -lt 16; $frame++) {
        $column = $frame % 4; $row = [math]::Floor($frame / 4)
        $left = [int][math]::Floor($column * $taskImage.Width / 4)
        $top = [int][math]::Floor($row * $taskImage.Height / 4)
        $right = [int][math]::Floor(($column+1) * $taskImage.Width / 4)
        $bottom = [int][math]::Floor(($row+1) * $taskImage.Height / 4)
        $destination = [System.Drawing.Rectangle]::new($column*384+2,$row*288+2,380,284)
        $taskGraphics.DrawImage($taskImage,$destination,$left,$top,$right-$left,$bottom-$top,[System.Drawing.GraphicsUnit]::Pixel)
    }
    $taskAtlas.Save($taskTarget,[System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $taskGraphics.Dispose(); $taskAtlas.Dispose(); $taskImage.Dispose()
}
$taskHash = (Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant()
$taskSourceHash = (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
$taskCatalogPath = Join-Path $taskRoot 'content/visual_assets.json'
$taskCatalog = Get-Content -LiteralPath $taskCatalogPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
$taskCatalog.assets['effect.tidal_wave.keyframes'] = @{
    file='/assets/pixel/tide/water-keyframes.png'; size=@(1536,1152); sha256=$taskHash; requires=@()
}
$taskCatalog | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $taskCatalogPath -Encoding utf8
$taskPrompt = Get-Content (Join-Path $taskRoot 'design/tide-water-20261028/prompt.json') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
$taskPrompt['padding_edit'] = Get-Content (Join-Path $taskRoot 'design/tide-water-20261028/padding-prompt.json') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
@{
    generator='OpenAI built-in image_gen'; source='design/tide-water-20261028/water-keyframes.png';
    source_sha256=$taskSourceHash; sha256=$taskHash; grid=@(4,4); cell=@(384,288);
    frames=16; stages=@('charge','travel','impact','dissipate'); prompt=$taskPrompt;
    export='Fixed grid crop and nearest-neighbour packing with two-pixel transparent gutters; no procedural water painting'
} | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $taskRoot 'web/assets/pixel/tide/water-provenance.json') -Encoding utf8
Write-Output 'Exported 16 painted water keyframes'
