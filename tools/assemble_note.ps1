# Збирає пояснювальну записку в один документ за допомогою Microsoft Word.
#
# Порядок частин (за вимогою викладача): титулка → завдання → анотація →
# зміст → вступ → розділи 1–4 → висновки → список джерел → додатки.
# Титулка, завдання й анотація заповнюються в шаблонах викладача (каталог
# templates/), решту генерує tools/build_note.js у build/note/.
#
# Запуск з кореня проєкту:  powershell -File tools\assemble_note.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$work = Join-Path $root "build\note"
# Шаблони викладача лежать локально в build\templates (до репозиторію не входять).
$templates = Join-Path $root "build\templates"
$outDocx = Join-Path $root "docs\Пояснювальна_записка_Курас_Автосервіс.docx"
$outPdf = [IO.Path]::ChangeExtension($outDocx, ".pdf")
$stats = Get-Content (Join-Path $work "stats.json") -Raw | ConvertFrom-Json

# Константи Word
$wdSectionBreakNextPage = 2
$wdHeaderFooterPrimary = 1
$wdHeaderFooterFirstPage = 2
$wdStatisticPages = 2
$wdActiveEndPageNumber = 3
$wdGoToPage = 1
$wdGoToAbsolute = 1
$wdFieldPage = 33
$wdFormatXMLDocument = 12
$wdFormatPDF = 17
$wdOrientLandscape = 1
$wdAlignTabCenter = 1
$wdAlignTabRight = 2
$wdAlignParagraphRight = 2

function Pt([double]$twips) { return $twips / 20.0 }

function Replace-Text($doc, [string]$find, [string]$replacement) {
    $range = $doc.Content
    $found = $range.Find.Execute($find, $true, $false, $false, $false,
        $false, $true, 0, $false, $replacement, 2)
    if (-not $found) { Write-Warning "Не знайдено в шаблоні: $find" }
}

function Set-Margins($section, $top, $right, $bottom, $left, $landscape) {
    $setup = $section.PageSetup
    if ($landscape) { $setup.Orientation = $wdOrientLandscape }
    $setup.TopMargin = Pt $top
    $setup.RightMargin = Pt $right
    $setup.BottomMargin = Pt $bottom
    $setup.LeftMargin = Pt $left
    $setup.HeaderDistance = Pt 567
}

function Write-Header($section, $kind, [string]$title) {
    # Номер сторінки праворуч; для додатків — назва по центру. Як у шаблоні
    # Додатка А, назва й номер стоять у таблиці без рамок із трьох комірок.
    $header = $section.Headers.Item($kind)
    $header.LinkToPrevious = $false
    $header.Range.Text = ""
    $header.Range.Font.Name = "Times New Roman"
    $header.Range.Font.Size = 14
    $header.Range.Font.Color = -16777216
    $header.Range.ParagraphFormat.SpaceAfter = 0
    if ($title -eq "") {
        $header.Range.ParagraphFormat.Alignment = $wdAlignParagraphRight
        [void]$header.Range.Fields.Add($header.Range, $wdFieldPage)
        return
    }
    $setup = $section.PageSetup
    $width = $setup.PageWidth - $setup.LeftMargin - $setup.RightMargin
    $table = $header.Range.Tables.Add($header.Range, 1, 3)
    $table.Borders.Enable = $false
    $table.Columns.Item(1).Width = $width * 0.2
    $table.Columns.Item(2).Width = $width * 0.6
    $table.Columns.Item(3).Width = $width * 0.2
    $table.Range.Font.Name = "Times New Roman"
    $table.Range.Font.Size = 14
    $table.Cell(1, 2).Range.Text = $title
    $table.Cell(1, 2).Range.ParagraphFormat.Alignment = 1
    $cell = $table.Cell(1, 3).Range
    $cell.ParagraphFormat.Alignment = $wdAlignParagraphRight
    $cell.Collapse(1)
    [void]$header.Range.Fields.Add($cell, $wdFieldPage)
}

function Prepare-Template($doc) {
    # Червоним у шаблонах викладач позначив поля для заміни; у готовому
    # документі текст чорний. Рядки шаблонів не повинні потрапляти в зміст.
    $doc.Content.Font.Color = -16777216
    $doc.Content.ParagraphFormat.OutlineLevel = 10
}
function Clear-Header($section) {
    foreach ($kind in @($wdHeaderFooterPrimary, $wdHeaderFooterFirstPage)) {
        $header = $section.Headers.Item($kind)
        $header.LinkToPrevious = $false
        $header.Range.Text = ""
    }
}

function Append-File($doc, [string]$path) {
    $range = $doc.Content
    $range.Collapse(0)
    $range.InsertBreak($wdSectionBreakNextPage)
    $range = $doc.Content
    $range.Collapse(0)
    $range.InsertFile($path)
    return $doc.Sections.Item($doc.Sections.Count)
}

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    # ---- 1. Шаблони викладача ------------------------------------------
    $title = Join-Path $work "title.docx"
    $task = Join-Path $work "task.docx"
    $annotation = Join-Path $work "annotation.docx"
    Copy-Item (Join-Path $templates "Титулка_ІС.docx") $title -Force
    Copy-Item (Join-Path $templates "2_Завдання_ІС.docx") $task -Force
    Copy-Item (Join-Path $templates "АНОТАЦІЯ_ІС.docx") $annotation -Force

    $doc = $word.Documents.Open($title)
    Replace-Text $doc "«…»" "«Автосервіс»"
    Replace-Text $doc "КП.ІС-24-01.07.01.00.000 ПЗ" "КП.ІС-24-01.__.01.00.000 ПЗ"
    Replace-Text $doc "Приймак В.І." "Курас А.В."
    Prepare-Template $doc
    # Шаблон титулки у Word переповзає на другу сторінку: між «Дата захисту»
    # і «Івано-Франківськ» шість порожніх рядків. Лишаємо два.
    $cityIndex = 0
    for ($i = 1; $i -le $doc.Paragraphs.Count; $i++) {
        $line = $doc.Paragraphs.Item($i).Range.Text
        # Перша літера в шаблоні може бути латинською «I», тому шукаємо «Франківськ».
        if ($line.Length -lt 25 -and $line.Contains("Франківськ")) { $cityIndex = $i; break }
    }
    $removed = 0
    for ($i = $cityIndex - 1; $i -ge 1 -and $removed -lt 5; $i--) {
        $paragraph = $doc.Paragraphs.Item($i)
        if ($paragraph.Range.Text.Trim() -ne "") { break }
        $paragraph.Range.Font.Size = 2   # порожній рядок стає майже нульовим
        $removed++
    }
    $doc.Save(); $doc.Close()

    $doc = $word.Documents.Open($task)
    Replace-Text $doc "Соколюк Назар Романович" "Курас Арсеній Володимирович"
    Replace-Text $doc "«Бібліотека»" "«Автосервіс»"
    Replace-Text $doc "обсяг даних з предметної області бібліотека." `
        "обсяг даних з предметної області автосервіс: клієнти, автомобілі, механіки, прайс робіт, склад запчастин, замовлення-наряди."
    Replace-Text $doc "Соколюк Н.Р." "Курас А.В."
    Replace-Text $doc "5 Перелік графічного матеріалу" `
        "5 Перелік графічного матеріалу: ER-діаграма бази даних, діаграми класів, діаграма станів замовлення, діаграма послідовності, схема навігації інтерфейсу."
    Prepare-Template $doc
    $doc.Save(); $doc.Close()

    $doc = $word.Documents.Open($annotation)
    $paragraphs = $doc.Paragraphs
    $start = $paragraphs.Item(2).Range.Start
    $end = $paragraphs.Item($paragraphs.Count).Range.End - 1
    $text = @(
        "Курсовий проєкт виконаний на: {PAGES} сторінках формату А4 з $($stats.figures) рисунками, $($stats.tables) таблицями, $($stats.appendices) додатками та $($stats.sources) посиланням на використані джерела.",
        "Тема роботи: Розробка програмного додатку для роботи з базою даних предметної області «Автосервіс».",
        "Мета роботи – створити настільний застосунок для майстра-приймальника автосервісу, який автоматизує облік клієнтів і автомобілів, замовлень-нарядів на ремонт, виконаних робіт, запчастин на складі та механіків і показує підсумкові показники роботи сервісу.",
        "У роботі проаналізовано предметну область і сформульовано функціональні вимоги. Спроєктовано базу даних SQLite з 10 пов'язаних таблиць і 7 представлень, побудовано ER-діаграму, діаграми класів, станів і послідовності. Застосунок реалізовано мовою Python з графічним інтерфейсом PyQt5 і графіками Matplotlib; код розділено на шари моделей, доступу до даних, сервісів та інтерфейсу.",
        "Застосунок оформлює замовлення з перевіркою авто й механіка, списує запчастини зі складу в одній транзакції, веде статуси замовлення за патерном «Стан», рахує знижки, підтримує пошук, фільтрацію за кількома умовами, сортування за двома полями, імпорт накладної з CSV та експорт у CSV і JSON.",
        "Працездатність підтверджено 113 модульними тестами pytest і 34 приймальними перевірками через інтерфейс, зокрема на некоректних і граничних даних, порожній базі та після повторного запуску.",
        "Ключові слова: автосервіс, замовлення-наряд, склад запчастин, база даних, SQLite, Python, PyQt5, ООП, патерн «Стан», транзакція."
    ) -join "`r"
    $doc.Range($start, $end).Text = $text
    $range = $doc.Range($start, $doc.Content.End)
    $range.Font.Name = "Times New Roman"
    $range.Font.Size = 14
    $range.Font.Bold = $false
    $range.ParagraphFormat.Alignment = 3          # за шириною
    $range.ParagraphFormat.FirstLineIndent = 35.45  # 1,25 см
    $range.ParagraphFormat.LeftIndent = 0
    $range.ParagraphFormat.LineSpacingRule = 1    # 1,5 інтервалу
    $range.ParagraphFormat.SpaceAfter = 0
    $range.ParagraphFormat.SpaceBefore = 0
    Prepare-Template $doc
    $doc.Save(); $doc.Close()

    # ---- 2. Склеювання ------------------------------------------------------
    Copy-Item $title $outDocx -Force
    $final = $word.Documents.Open($outDocx)
    $taskSection = Append-File $final $task
    Set-Margins $taskSection 850 850 850 1417 $false
    $annotationSection = Append-File $final $annotation
    Set-Margins $annotationSection 850 850 850 1417 $false
    $bodySection = Append-File $final (Join-Path $work "body.docx")
    Set-Margins $bodySection 850 850 850 1417 $false
    $appendices = @(
        @{ File = "appendix_a.docx"; Letter = "А"; Landscape = $false },
        @{ File = "appendix_b.docx"; Letter = "Б"; Landscape = $false },
        @{ File = "appendix_c.docx"; Letter = "В"; Landscape = $true })
    $appendixSections = @()
    foreach ($item in $appendices) {
        $section = Append-File $final (Join-Path $work $item.File)
        Set-Margins $section 1134 567 1134 1418 $item.Landscape
        $appendixSections += @{ Index = $final.Sections.Count;
            Letter = $item.Letter }
    }

    # ---- 3. Колонтитули й нумерація ----------------------------------------
    # Титулка й завдання входять до нумерації, але номер на них не ставиться.
    Clear-Header $final.Sections.Item(1)
    Clear-Header $final.Sections.Item(2)
    for ($i = 3; $i -le 4; $i++) {
        $section = $final.Sections.Item($i)
        $section.PageSetup.DifferentFirstPageHeaderFooter = $false
        Write-Header $section $wdHeaderFooterPrimary ""
    }
    $final.Repaginate()
    # Додатки обробляються з кінця, бо розбиття додає нові розділи.
    [array]::Reverse($appendixSections)
    foreach ($item in $appendixSections) {
        $section = $final.Sections.Item($item.Index)
        $letter = $item.Letter
        $section.PageSetup.DifferentFirstPageHeaderFooter = $true
        Write-Header $section $wdHeaderFooterFirstPage ""
        Write-Header $section $wdHeaderFooterPrimary "ПРОДОВЖЕННЯ ДОДАТКУ $letter"
        $final.Repaginate()
        $first = $section.Range.Characters.First.Information($wdActiveEndPageNumber)
        $last = $section.Range.Characters.Last.Information($wdActiveEndPageNumber)
        if ($last -gt $first) {
            # Остання сторінка — окремий розділ із «ЗАКІНЧЕННЯ ДОДАТКУ».
            $pageStart = $final.GoTo($wdGoToPage, $wdGoToAbsolute, $last)
            $pageStart.InsertBreak($wdSectionBreakNextPage)
            $final.Repaginate()
            $tail = $final.Sections.Item($item.Index + 1)
            $tail.PageSetup.DifferentFirstPageHeaderFooter = $true
            Write-Header $tail $wdHeaderFooterFirstPage "ЗАКІНЧЕННЯ ДОДАТКУ $letter"
            Write-Header $tail $wdHeaderFooterPrimary "ЗАКІНЧЕННЯ ДОДАТКУ $letter"
        }
    }

    # ---- 4. Зміст, кількість сторінок -----------------------------------
    foreach ($styleId in @(-20, -21)) {
        $style = $final.Styles.Item($styleId)
        $style.Font.Name = "Times New Roman"
        $style.Font.Size = 14
        $style.Font.Bold = $false
        $style.ParagraphFormat.SpaceAfter = 0
        $style.ParagraphFormat.LineSpacingRule = 1   # 1,5 інтервалу
    }
    # До змісту потрапляють лише заголовки тіла записки й додатків: рядки
    # шаблонів титулки й завдання оформлені стилями заголовків.
    $bodyStart = $final.Sections.Item(4).Range.Start
    [void]$final.Bookmarks.Add("TocRange", $final.Range($bodyStart, $final.Content.End))
    foreach ($field in $final.Fields) {
        if ($field.Code.Text -match "TOC") {
            $field.Code.Text = ' TOC \o "1-2" \h \z \b TocRange '
        }
    }
    $final.TablesOfContents.Item(1).Update()
    $final.Repaginate()
    $pages = $final.ComputeStatistics($wdStatisticPages)
    Replace-Text $final "{PAGES}" "$pages"
    $final.TablesOfContents.Item(1).Update()
    $final.Save()
    $final.SaveAs2($outPdf, $wdFormatPDF)
    $final.Close()
    Write-Output "OK: $pages сторінок; $outDocx"
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
