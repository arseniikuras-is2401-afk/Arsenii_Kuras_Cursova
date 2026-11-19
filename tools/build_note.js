/*
 * Генерує пояснювальну записку курсового проєкту у форматі .docx.
 *
 * Запуск з кореня проєкту (бібліотека docx встановлюється в build/docgen):
 *   npm install --prefix build/docgen docx
 *   node tools/build_note.js [кількість_сторінок]
 *
 * Фрагменти коду беруться з вихідних файлів, тож записка відповідає
 * поточній версії програми.
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const docx = require(path.join(ROOT, "build", "docgen", "node_modules",
  "docx"));
const {
  AlignmentType, BorderStyle, Document, Footer, Header, HeadingLevel,
  ImageRun, LevelFormat, PageBreak, PageNumber, PageOrientation, Packer,
  Paragraph, ShadingType, Table, TableCell, TableOfContents, TableRow,
  TabStopType, TextRun, VerticalAlign, WidthType,
} = docx;

const OUT = path.join(ROOT, "docs",
  "Курас_ПЗ.docx");
const PAGES = process.argv[2] || "__";

// ---- оформлення за ДСТУ 3008:2015 -----------------------------------------
const FONT = "Times New Roman";
const MONO = "Courier New";
const SIZE = 28;            // 14 пт
const LINE = 360;           // інтервал 1,5
const INDENT = 709;         // абзацний відступ 1,25 см
const MM = 56.7;            // 1 мм у DXA
const PAGE_W = 11906;
const PAGE_H = 16838;
// Поля як у зразку ПЗ: 15 мм зверху, справа, знизу і 25 мм зліва.
const MARGIN = { top: 850, bottom: 850, left: 1417, right: 850 };
const TEXT_W = PAGE_W - MARGIN.left - MARGIN.right;   // ≈ 9355
const TEXT_W_LAND = PAGE_H - MARGIN.left - MARGIN.right;

let figureNo = 0;
let tableNo = 0;
let section = 0;
const counters = { figures: 0, tables: 0 };

// ---- текстові елементи --------------------------------------------------------

/** Розбирає **жирний** і `код` у рядку на фрагменти тексту. */
function runs(text, base = {}) {
  const parts = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(new TextRun({ text: text.slice(last, match.index),
        font: FONT, size: SIZE, ...base }));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(new TextRun({ text: token.slice(2, -2), bold: true,
        font: FONT, size: SIZE, ...base }));
    } else {
      parts.push(new TextRun({ text: token.slice(1, -1), font: MONO,
        size: SIZE - 4, ...base }));
    }
    last = match.index + token.length;
  }
  if (last < text.length) {
    parts.push(new TextRun({ text: text.slice(last), font: FONT, size: SIZE,
      ...base }));
  }
  return parts;
}

function p(text, options = {}) {
  return new Paragraph({
    children: runs(text),
    alignment: options.align || AlignmentType.JUSTIFIED,
    indent: { firstLine: options.noIndent ? 0 : INDENT },
    spacing: { line: LINE, before: 0, after: 0 },
    keepNext: options.keepNext,
  });
}

function centered(text, options = {}) {
  return new Paragraph({
    children: [new TextRun({ text, font: FONT, size: options.size || SIZE,
      bold: options.bold, allCaps: options.caps })],
    alignment: AlignmentType.CENTER,
    spacing: { line: options.line || LINE, before: options.before || 0,
      after: options.after || 0 },
  });
}

function blank(count = 1) {
  return Array.from({ length: count }, () => new Paragraph({
    children: [new TextRun({ text: "", font: FONT, size: SIZE })],
    spacing: { line: LINE } }));
}

/** Структурний елемент без номера: ВСТУП, ВИСНОВКИ… */
function heading0(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text: text.toUpperCase(), font: FONT,
      size: SIZE, bold: true })],
    alignment: AlignmentType.CENTER,
    pageBreakBefore: true,
    spacing: { line: LINE, before: 0, after: 280 },
  });
}

function heading1(number, text) {
  section = number;
  figureNo = 0;
  tableNo = 0;
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text: `${number} ${text.toUpperCase()}`,
      font: FONT, size: SIZE, bold: true })],
    alignment: AlignmentType.CENTER,
    pageBreakBefore: true,
    spacing: { line: LINE, before: 0, after: 280 },
  });
}

function heading2(number, text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text: `${number} ${text}`, font: FONT,
      size: SIZE, bold: true })],
    indent: { firstLine: INDENT },
    keepNext: true,
    spacing: { line: LINE, before: 280, after: 140 },
  });
}

function heading3(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: FONT, size: SIZE, bold: true,
      italics: true })],
    indent: { firstLine: INDENT },
    keepNext: true,
    spacing: { line: LINE, before: 120, after: 60 },
  });
}

function bullets(items) {
  return items.map((item) => new Paragraph({
    children: runs(item),
    numbering: { reference: "dash", level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: LINE },
  }));
}

function numbered(items, reference) {
  return items.map((item) => new Paragraph({
    children: runs(item),
    numbering: { reference, level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: LINE },
  }));
}

// ---- таблиці --------------------------------------------------------------------

const CELL_BORDER = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const BORDERS = { top: CELL_BORDER, bottom: CELL_BORDER, left: CELL_BORDER,
  right: CELL_BORDER };

function cell(text, width, options = {}) {
  const lines = String(text).split("\n");
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: BORDERS,
    verticalAlign: VerticalAlign.TOP,
    shading: options.header ? { type: ShadingType.CLEAR, color: "auto",
      fill: "E7E7E7" } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    children: lines.map((line) => new Paragraph({
      children: runs(line, { size: options.size || 24,
        bold: options.header || undefined }).map((run) => run),
      alignment: options.header ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { line: 240 },
    })),
  });
}

function tableCaption(title) {
  tableNo += 1;
  counters.tables += 1;
  const label = `${section}.${tableNo}`;
  return {
    label,
    paragraph: new Paragraph({
      children: [new TextRun({ text: `Таблиця ${label} – ${title}`,
        font: FONT, size: SIZE })],
      keepNext: true,
      spacing: { line: LINE, before: 120, after: 60 },
    }),
  };
}

/** Таблиця з підписом; widths — частки, що масштабуються до ширини тексту. */
function table(title, headers, rows, weights, options = {}) {
  const total = weights.reduce((sum, item) => sum + item, 0);
  const widths = weights.map((item) => Math.floor(item / total *
    (options.width || TEXT_W)));
  widths[widths.length - 1] += (options.width || TEXT_W) -
    widths.reduce((sum, item) => sum + item, 0);
  const size = options.size || 24;
  const caption = tableCaption(title);
  const result = new Table({
    width: { size: options.width || TEXT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((head, index) =>
        cell(head, widths[index], { header: true, size })) }),
      ...rows.map((row) => new TableRow({ cantSplit: true,
        children: row.map((value, index) => cell(value, widths[index],
          { size })) })),
    ],
  });
  return [caption.paragraph, result, ...blank()];
}

// ---- рисунки -------------------------------------------------------------------

function pngSize(file) {
  const data = fs.readFileSync(file);
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
}

function figure(relative, title, widthCm = 16, maxHeightCm = 21) {
  const file = path.join(ROOT, relative);
  const size = pngSize(file);
  let width = widthCm / 2.54 * 96;
  let height = width * size.height / size.width;
  const maxHeight = maxHeightCm / 2.54 * 96;
  if (height > maxHeight) {
    width *= maxHeight / height;
    height = maxHeight;
  }
  figureNo += 1;
  counters.figures += 1;
  const label = `${section}.${figureNo}`;
  return [
    new Paragraph({
      children: [new ImageRun({ type: "png", data: fs.readFileSync(file),
        transformation: { width: Math.round(width),
          height: Math.round(height) },
        altText: { title, description: title, name: path.basename(file) },
      })],
      alignment: AlignmentType.CENTER,
      keepNext: true,
      spacing: { before: 120, after: 60 },
    }),
    new Paragraph({
      children: [new TextRun({ text: `Рисунок ${label} – ${title}`,
        font: FONT, size: SIZE })],
      alignment: AlignmentType.CENTER,
      spacing: { line: LINE, after: 160 },
    }),
  ];
}

function figureLabel() {
  return `${section}.${figureNo + 1}`;
}

function tableLabel() {
  return `${section}.${tableNo + 1}`;
}

// ---- код ----------------------------------------------------------------------

function codeLines(lines, size = 20) {
  return lines.map((line) => new Paragraph({
    children: [new TextRun({ text: line.replace(/\t/g, "    ") || " ",
      font: MONO, size })],
    spacing: { line: size * 10 + 20, lineRule: "exact", before: 0,
      after: 0 },
  }));
}

function read(relative) {
  return fs.readFileSync(path.join(ROOT, relative), "utf8")
    .replace(/\r\n/g, "\n");
}

/** Фрагмент: рядок з `signature` і наступні рядки з більшим відступом. */
function snippet(relative, signature, maxLines = 40) {
  const lines = read(relative).split("\n");
  const start = lines.findIndex((line) => line.includes(signature));
  if (start < 0) {
    throw new Error(`Не знайдено «${signature}» у ${relative}`);
  }
  const indent = lines[start].match(/^\s*/)[0].length;
  const result = [lines[start]];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim() && line.match(/^\s*/)[0].length <= indent &&
        !line.trim().startsWith(")")) {
      break;
    }
    result.push(line);
  }
  while (result.length && !result[result.length - 1].trim()) {
    result.pop();
  }
  const shown = result.slice(0, maxLines).map((line) => line.slice(indent));
  if (result.length > maxLines) {
    shown.push("    ...");
  }
  return shown;
}

function codeBlock(relative, signature, title, maxLines) {
  return [
    p(`Лістинг ${title} (файл ${relative}):`, { keepNext: true }),
    new Paragraph({ children: [], spacing: { after: 60 } }),
    ...codeLines(snippet(relative, signature, maxLines)),
    new Paragraph({ children: [], spacing: { after: 160 } }),
  ];
}

// ---- дані з інших файлів ----------------------------------------------------

function sourceFiles() {
  const order = ["main.py", "config.py", "models", "database", "services",
    "ui"];
  const files = [];
  const walk = (relative) => {
    const full = path.join(ROOT, relative);
    if (fs.statSync(full).isFile()) {
      files.push(relative);
      return;
    }
    fs.readdirSync(full).sort().forEach((name) => {
      if (name === "__pycache__") {
        return;
      }
      const child = path.join(relative, name);
      if (fs.statSync(path.join(ROOT, child)).isDirectory() ||
          name.endsWith(".py")) {
        walk(child);
      }
    });
  };
  order.forEach(walk);
  return files.map((file) => file.replace(/\\/g, "/"));
}

module.exports = {
  AlignmentType, Document, Footer, Header, LevelFormat, PageBreak,
  PageNumber, PageOrientation, Packer, Paragraph, TabStopType,
  TableOfContents, TextRun, FONT, MONO, SIZE, LINE, INDENT, MARGIN, PAGE_W,
  PAGE_H, TEXT_W, TEXT_W_LAND, OUT, PAGES, ROOT, counters, p, centered,
  blank, heading0, heading1, heading2, heading3, bullets, numbered, table,
  figure, figureLabel, tableLabel, codeLines, codeBlock, read,
  sourceFiles, runs, cell,
  setSection: (number) => { section = number; figureNo = 0; tableNo = 0; },
};

if (require.main === module) {
  require("./note_content.js").build();
}
