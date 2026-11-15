/*
 * Презентація для захисту курсового проєкту (pptxgenjs).
 *
 *   npm install --prefix build/docgen pptxgenjs
 *   node tools/build_deck.js
 *
 * Дані графіка виручки — build/note/deck_data.json (з демо-бази).
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const pptxgen = require(path.join(ROOT, "build", "docgen", "node_modules",
  "pptxgenjs"));
const SKILL_THEME = process.env.PPTX_APPLY_THEME;
const OUT = path.join(ROOT, "docs", "Презентація_Курас_Автосервіс.pptx");

// Палітра застосунку: графітова бічна панель і помаранчевий акцент.
const COLORS = {
  dark: "1B2130", darkSoft: "2A3245", light: "F5F6F8", white: "FFFFFF",
  text: "1D2330", muted: "667085", line: "E2E5EA", accent: "C2410C",
  accentBright: "F97316", accentSoft: "FFEDD5", green: "2B8A3E",
};
const THEME = {
  name: "Автосервіс",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: { dk1: COLORS.text, lt1: COLORS.white, dk2: COLORS.dark,
    lt2: COLORS.light, accent1: COLORS.accent, accent2: COLORS.accentBright,
    accent3: COLORS.green, accent4: "1C64C2", accent5: "6741D9",
    accent6: COLORS.muted, hlink: COLORS.accent, folHlink: COLORS.muted },
};

function readData() {
  const raw = fs.readFileSync(path.join(ROOT, "build", "note",
    "deck_data.json"));
  const text = raw[0] === 0xff && raw[1] === 0xfe ?
    raw.toString("utf16le").slice(1) : raw.toString("utf8");
  return JSON.parse(text.trim());
}

function pngSize(file) {
  const data = fs.readFileSync(file);
  return { w: data.readUInt32BE(16), h: data.readUInt32BE(20) };
}

/** Картинка, вписана в прямокутник із збереженням пропорцій. */
function fit(file, box) {
  const size = pngSize(file);
  const scale = Math.min(box.w / size.w, box.h / size.h);
  const w = size.w * scale;
  const h = size.h * scale;
  return { path: file, x: box.x + (box.w - w) / 2, y: box.y + (box.h - h) / 2,
    w, h };
}

const shot = (name) => path.join(ROOT, "docs", "screenshots", `${name}.png`);
const diagram = (name) => path.join(ROOT, "docs", "diagrams", `${name}.png`);

async function build() {
  const data = readData();
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";            // 13,333 × 7,5 дюйма
  pres.author = "Курас Арсеній Володимирович";
  pres.title = "Автосервіс — курсовий проєкт";
  pres.theme = { headFontFace: THEME.headFontFace,
    bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: COLORS.light },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6,
        y: 0.35, w: 12.1, h: 0.8, fontSize: 32, bold: true,
        color: COLORS.text, valign: "middle", margin: 0 },
      text: "Заголовок" } },
      { text: { text: "Курас Арсеній · Автосервіс", options: { x: 0.6,
        y: 7.0, w: 6, h: 0.3, fontSize: 10, color: COLORS.muted,
        margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10,
      color: COLORS.muted, align: "right" },
  });
  pres.defineSlideMaster({ title: "DARK",
    background: { color: COLORS.dark } });

  const card = (slide, x, y, w, h, name) => slide.addShape(
    pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12,
      fill: { color: COLORS.white }, line: { color: COLORS.line, width: 1 },
      objectName: name });
  const badge = (slide, x, y, label) => {
    slide.addShape(pres.shapes.OVAL, { x, y, w: 0.55, h: 0.55,
      fill: { color: COLORS.accentSoft }, line: { color: COLORS.accentSoft },
      objectName: `badge ${label}` });
    slide.addText(label, { x, y, w: 0.55, h: 0.55, align: "center",
      valign: "middle", fontSize: 16, bold: true, color: COLORS.accent,
      margin: 0, isTextBox: true });
  };
  const textBlock = (slide, x, y, w, h, title, body, size = 14) => {
    slide.addText([
      { text: title, options: { bold: true, fontSize: size + 2,
        color: COLORS.text, breakLine: true } },
      { text: body, options: { fontSize: size, color: COLORS.muted } },
    ], { x, y, w, h, valign: "top", margin: 0, paraSpaceAfter: 4,
      isTextBox: true });
  };
  const bullets = (slide, items, box, size = 16) => slide.addText(
    items.map((item, index) => ({ text: item, options: { bullet: true,
      breakLine: index < items.length - 1 } })),
    { ...box, fontSize: size, color: COLORS.text, paraSpaceAfter: 10,
      valign: "top", margin: 0, isTextBox: true });

  // 1. Титул --------------------------------------------------------------------
  pres.addSection({ title: "Вступ" });
  let slide = pres.addSlide({ masterName: "DARK", sectionTitle: "Вступ" });
  slide.addText("КУРСОВИЙ ПРОЄКТ · ОБ'ЄКТНО-ОРІЄНТОВАНЕ ПРОГРАМУВАННЯ", {
    x: 0.8, y: 0.8, w: 11.5, h: 0.4, fontSize: 14, bold: true,
    color: COLORS.accentBright, charSpacing: 2, margin: 0, isTextBox: true });
  slide.addText("Автосервіс", { x: 0.8, y: 1.5, w: 11.5, h: 1.3,
    fontSize: 60, bold: true, color: COLORS.white, margin: 0,
    isTextBox: true });
  slide.addText("Розробка програмного додатку для роботи з базою даних " +
    "предметної області «Автосервіс»", { x: 0.8, y: 2.9, w: 10.5, h: 1.0,
    fontSize: 22, color: "AEB6C4", margin: 0, isTextBox: true });
  slide.addText([
    { text: "Виконав: ", options: { color: "AEB6C4" } },
    { text: "Курас Арсеній Володимирович", options: { bold: true,
      color: COLORS.white, breakLine: true } },
    { text: "Керівник: ", options: { color: "AEB6C4" } },
    { text: "викладач Стражник О. Я.", options: { color: COLORS.white,
      breakLine: true } },
    { text: "ВСП «Фаховий коледж електронних приладів ІФНТУНГ», 2026",
      options: { color: "AEB6C4" } },
  ], { x: 0.8, y: 4.9, w: 9, h: 1.4, fontSize: 16, paraSpaceAfter: 6,
    margin: 0, isTextBox: true });
  slide.addImage({ ...fit(shot("01_dashboard"), { x: 8.9, y: 4.3, w: 4.0,
    h: 2.6 }), objectName: "screenshot dashboard",
  altText: "Головна сторінка застосунку" });
  slide.addNotes("Представлення теми, автора й керівника.");

  // 2. Проблема й мета --------------------------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Вступ" });
  slide.addText("Навіщо автосервісу ця програма", { placeholder: "title" });
  const problems = [
    ["1", "Історія ремонтів", "Замовлення в зошиті: важко знайти, що вже " +
      "ремонтували в конкретному авто"],
    ["2", "Вартість і склад", "Сума із запчастинами й знижками рахується " +
      "вручну, залишки деталей невідомі"],
    ["3", "Навантаження", "Незрозуміло, хто з механіків перевантажений і " +
      "які замовлення прострочені"],
  ];
  problems.forEach(([n, title, body], i) => {
    const x = 0.6 + i * 4.1;
    card(slide, x, 1.5, 3.8, 2.4, `problem ${n}`);
    badge(slide, x + 0.3, 1.8, n);
    textBlock(slide, x + 0.3, 2.5, 3.2, 1.3, title, body);
  });
  card(slide, 0.6, 4.3, 12.1, 2.4, "goal");
  slide.addText([
    { text: "Мета: ", options: { bold: true, color: COLORS.accent } },
    { text: "настільний застосунок для майстра-приймальника, який веде " +
      "клієнтів і авто, оформлює замовлення-наряди від приймання до " +
      "оплати, списує запчастини зі складу й показує підсумкові " +
      "показники." },
  ], { x: 1.0, y: 4.6, w: 11.3, h: 1.8, fontSize: 20, color: COLORS.text,
    valign: "middle", margin: 0, isTextBox: true });
  slide.addNotes("Проблема ручного обліку й мета проєкту.");

  // 3. Архітектура --------------------------------------------------------------
  pres.addSection({ title: "Проєктування" });
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Проєктування" });
  slide.addText("Чотири шари з розподілом відповідальності",
    { placeholder: "title" });
  const layers = [
    ["ui", "PyQt5: вікно, 8 сторінок, форми, фільтри, графіки Matplotlib"],
    ["services", "Сценарії й правила, транзакції, події, імпорт і експорт"],
    ["database", "SQLite: Unit of Work, DAO таблиць, пошук і сортування"],
    ["models", "Order, Car, Part, Money, стани й знижки — без Qt і SQL"],
  ];
  layers.forEach(([name, body], i) => {
    const y = 1.5 + i * 1.3;
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 2.2,
      h: 1.0, rectRadius: 0.12, fill: { color: i === 0 ? COLORS.accent :
        COLORS.dark }, line: { color: COLORS.dark },
      objectName: `layer ${name}` });
    slide.addText(name, { x: 0.6, y, w: 2.2, h: 1.0, align: "center",
      valign: "middle", fontSize: 20, bold: true, color: COLORS.white,
      margin: 0, isTextBox: true });
    slide.addText(body, { x: 3.1, y, w: 4.6, h: 1.0, fontSize: 15,
      color: COLORS.text, valign: "middle", margin: 0, isTextBox: true });
  });
  card(slide, 8.2, 1.5, 4.5, 4.9, "tech");
  slide.addText("Технології", { x: 8.5, y: 1.7, w: 3.9, h: 0.5,
    fontSize: 18, bold: true, color: COLORS.text, margin: 0,
    isTextBox: true });
  bullets(slide, ["Python 3.14", "PyQt5 5.15", "SQLite (sqlite3)",
    "Matplotlib", "pytest — 113 тестів", "Залежності йдуть лише вниз: " +
    "моделі тестуються без інтерфейсу"], { x: 8.5, y: 2.3, w: 3.9, h: 3.9 },
  15);
  slide.addNotes("Шари ui → services → database → models.");

  // 4. База даних ----------------------------------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Проєктування" });
  slide.addText("База даних: 10 пов'язаних таблиць", { placeholder: "title" });
  card(slide, 0.6, 1.4, 6.6, 5.4, "er frame");
  slide.addImage({ ...fit(diagram("er_diagram"), { x: 0.8, y: 1.55, w: 6.2,
    h: 5.1 }), objectName: "ER diagram", altText: "ER-діаграма" });
  const stats = [["10", "таблиць з PK/FK"], ["7", "представлень для списків"],
    ["0 коп.", "похибки: гроші в копійках"], ["1", "транзакція на дію"]];
  stats.forEach(([value, label], i) => {
    const x = 7.6 + (i % 2) * 2.6;
    const y = 1.5 + Math.floor(i / 2) * 1.75;
    slide.addText(value, { x, y, w: 2.4, h: 0.9, fontSize: 40, bold: true,
      color: COLORS.accent, margin: 0, isTextBox: true });
    slide.addText(label, { x, y: y + 0.9, w: 2.4, h: 0.6, fontSize: 13,
      color: COLORS.muted, margin: 0, isTextBox: true });
  });
  bullets(slide, ["RESTRICT: клієнта з авто не видалити", "CASCADE: рядки " +
    "живуть лише з замовленням", "CHECK: залишок ≥ 0, знижка 0–30 %"],
  { x: 7.6, y: 5.0, w: 5.1, h: 1.8 }, 14);
  slide.addNotes("Таблиці, ключі, правила видалення, гроші в копійках.");

  // 5. ООП --------------------------------------------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Проєктування" });
  slide.addText("Принципи ООП у коді", { placeholder: "title" });
  const oop = [
    ["Інкапсуляція", "Part.stock_qty без сетера: залишок змінюють лише " +
      "take() і put_back(), тож він не стане від'ємним"],
    ["Композиція", "Order створює й видаляє свої рядки; UnitOfWork керує " +
      "DAO на одному з'єднанні"],
    ["Успадкування", "Person → Client, Employee; OrderLine → WorkLine, " +
      "PartLine; Page → 8 сторінок"],
    ["Поліморфізм", "Стани замовлення, політики знижок, фільтри й поля форм " +
      "працюють через спільний інтерфейс"],
  ];
  oop.forEach(([title, body], i) => {
    const x = 0.6 + (i % 2) * 6.15;
    const y = 1.5 + Math.floor(i / 2) * 2.7;
    card(slide, x, y, 5.95, 2.45, `oop ${title}`);
    badge(slide, x + 0.3, y + 0.3, String(i + 1));
    textBlock(slide, x + 1.1, y + 0.3, 4.5, 1.9, title, body, 15);
  });
  slide.addNotes("Приклади кожного принципу з коду.");

  // 6. Статуси --------------------------------------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Проєктування" });
  slide.addText("Статуси замовлення: патерн «Стан»",
    { placeholder: "title" });
  card(slide, 0.6, 1.4, 5.6, 5.4, "state frame");
  slide.addImage({ ...fit(diagram("state_order"), { x: 0.8, y: 1.55, w: 5.2,
    h: 5.1 }), objectName: "state diagram", altText: "Діаграма станів" });
  bullets(slide, [
    "Кожен статус — окремий клас: знає дозволені переходи, перевірки й дії",
    "«В роботі» — лише якщо є хоча б одна робота",
    "«Виконано» оновлює пробіг авто",
    "«Скасовано» повертає запчастини на склад",
    "Вікно замовлення будує кнопки з allowed_next()",
  ], { x: 6.7, y: 1.6, w: 6.0, h: 5.0 }, 17);
  slide.addNotes("Без if/elif за статусами — поведінку делеговано стану.");

  // 7. Інтерфейс ------------------------------------------------------------------
  pres.addSection({ title: "Реалізація" });
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Реалізація" });
  slide.addText("Інтерфейс: 8 розділів і показники дня",
    { placeholder: "title" });
  slide.addImage({ ...fit(shot("01_dashboard"), { x: 0.6, y: 1.4, w: 8.2,
    h: 5.4 }), objectName: "dashboard", altText: "Головна сторінка" });
  bullets(slide, ["Картки показників ведуть до відфільтрованих списків",
    "Прострочені замовлення й дефіцит — одразу на головній",
    "Сторінки оновлюються самі після змін (EventHub)",
    "Ім'я автора — на бічній панелі й у «Про програму»"],
  { x: 9.2, y: 1.6, w: 3.5, h: 5.0 }, 15);
  slide.addNotes("Демонстрація головної сторінки.");

  // 8. Замовлення -------------------------------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Реалізація" });
  slide.addText("Замовлення-наряд в одній транзакції",
    { placeholder: "title" });
  slide.addImage({ ...fit(shot("10_order_window"), { x: 0.6, y: 1.4, w: 6.4,
    h: 5.4 }), objectName: "order window", altText: "Вікно замовлення" });
  bullets(slide, ["Одне відкрите замовлення на авто, ≤ 4 у механіка",
    "Запчастина списується разом із рядком або не списується зовсім",
    "Ціна фіксується в момент додавання",
    "Знижки: 5 % постійному клієнту, до 30 % від майстра, діє більша",
    "Помилка посередині — rollback, дані не змінюються"],
  { x: 7.4, y: 1.6, w: 5.3, h: 5.0 }, 16);
  slide.addNotes("Вікно замовлення й бізнес-правила.");

  // 9. Пошук, фільтри, імпорт ------------------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Реалізація" });
  slide.addText("Пошук, фільтри, сортування, імпорт і експорт",
    { placeholder: "title" });
  slide.addImage({ ...fit(shot("06_orders_filters"), { x: 0.6, y: 1.4,
    w: 7.6, h: 5.4 }), objectName: "filters", altText: "Фільтри" });
  bullets(slide, ["Пошук за кількома полями, кирилиця без регістру",
    "3–4 фільтри одночасно + сортування за двома полями",
    "Назви полів — лише з білого списку: SQL-ін'єкція неможлива",
    "Імпорт накладної CSV: UTF-8 / 1251, звіт з номерами рядків",
    "Експорт поточної вибірки в CSV (Excel) або JSON"],
  { x: 8.6, y: 1.6, w: 4.1, h: 5.0 }, 15);
  slide.addNotes("Робота зі списками й файлами.");

  // 10. Статистика (нативний графік) -----------------------------------------
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Реалізація" });
  slide.addText("Статистика: виручка по місяцях", { placeholder: "title" });
  card(slide, 0.6, 1.4, 8.4, 5.4, "chart frame");
  slide.addChart(pres.charts.BAR, [{ name: "Виручка, грн",
    labels: data.labels, values: data.values }], {
    x: 0.8, y: 1.55, w: 8.0, h: 5.1, barDir: "col",
    chartColors: [COLORS.accentBright], showValue: true,
    dataLabelPosition: "outEnd", dataLabelFontSize: 11,
    dataLabelColor: COLORS.muted, dataLabelFormatCode: "# ##0",
    dataLabelFontFace: "+mn-lt", catAxisLabelFontFace: "+mn-lt",
    valAxisLabelFontFace: "+mn-lt", catAxisLabelColor: COLORS.muted,
    valAxisLabelColor: COLORS.muted, catAxisLabelFontSize: 12,
    valAxisLabelFontSize: 11, valGridLine: { color: COLORS.line, size: 1 },
    catGridLine: { style: "none" }, valAxisLabelFormatCode: "# ##0",
    showLegend: false, showTitle: true,
    title: "Оплачені замовлення, грн", titleFontSize: 14,
    titleColor: COLORS.text, titleFontFace: "+mn-lt",
    objectName: "revenue chart" });
  const total = data.values.reduce((sum, value) => sum + value, 0);
  slide.addText(`${Math.round(total).toLocaleString("uk-UA")} грн`, {
    x: 9.4, y: 1.6, w: 3.4, h: 0.9, fontSize: 32, bold: true,
    color: COLORS.accent, margin: 0, isTextBox: true });
  slide.addText("виручка за 6 місяців демо-даних", { x: 9.4, y: 2.5, w: 3.4,
    h: 0.5, fontSize: 13, color: COLORS.muted, margin: 0, isTextBox: true });
  bullets(slide, ["Графіки Matplotlib у вікні PyQt5",
    "Вибір періоду й механіка", "Топ робіт і завантаженість механіків",
    "Суми збігаються з таблицею замовлень (перевірено тестом)"],
  { x: 9.4, y: 3.3, w: 3.4, h: 3.4 }, 14);
  slide.addNotes("Графік побудовано з даних демонстраційної бази.");

  // 11. Тестування ---------------------------------------------------------------
  pres.addSection({ title: "Результати" });
  slide = pres.addSlide({ masterName: "CONTENT",
    sectionTitle: "Результати" });
  slide.addText("Тестування", { placeholder: "title" });
  const results = [["113", "модульних тестів pytest"],
    ["34 / 34", "приймальні перевірки через інтерфейс"],
    ["150", "демо-замовлень: суми SQL = Python"]];
  results.forEach(([value, label], i) => {
    const x = 0.6 + i * 4.1;
    card(slide, x, 1.5, 3.8, 2.1, `result ${i}`);
    slide.addText(value, { x: x + 0.3, y: 1.7, w: 3.2, h: 1.0, fontSize: 44,
      bold: true, color: COLORS.accent, margin: 0, isTextBox: true });
    slide.addText(label, { x: x + 0.3, y: 2.75, w: 3.2, h: 0.7,
      fontSize: 14, color: COLORS.muted, margin: 0, isTextBox: true });
  });
  bullets(slide, [
    "Некоректні й граничні дані: телефон, держномер, знижка > 30 %, " +
    "запчастин більше за залишок",
    "Цілісність: видалення з залежностями, недозволені переходи статусів, " +
    "збій посередині транзакції",
    "Порожня база, порожній пошук, повторний запуск без дублювання",
    "Скрипт сам робить скриншоти й таблицю перевірок для записки",
  ], { x: 0.6, y: 4.0, w: 12.1, h: 2.8 }, 17);
  slide.addNotes("Підсумки тестування.");

  // 12. Висновки -------------------------------------------------------------------
  slide = pres.addSlide({ masterName: "DARK", sectionTitle: "Результати" });
  slide.addText("Висновки", { x: 0.8, y: 0.7, w: 11.5, h: 1.0, fontSize: 40,
    bold: true, color: COLORS.white, margin: 0, isTextBox: true });
  slide.addText([
    "Застосунок виконує всі функціональні вимоги I рівня",
    "База SQLite з 10 таблиць, обмеженнями й транзакціями",
    "Інкапсуляція, композиція, успадкування й поліморфізм — у реальних " +
    "класах",
    "Сучасний інтерфейс PyQt5 з автооновленням і перевіркою введення",
    "Далі: часткові оплати, друк наряду в PDF, ролі користувачів",
  ].map((item, index, all) => ({ text: item, options: { bullet: true,
    breakLine: index < all.length - 1 } })), { x: 0.8, y: 2.0, w: 11.5,
    h: 3.8, fontSize: 20, color: "D7DCE4", paraSpaceAfter: 12, margin: 0,
    valign: "top", isTextBox: true });
  slide.addText("Дякую за увагу!", { x: 0.8, y: 6.1, w: 11.5, h: 0.6,
    fontSize: 22, bold: true, color: COLORS.accentBright, margin: 0,
    isTextBox: true });
  slide.addNotes("Підсумки й напрями розвитку.");

  void C;
  await pres.writeFile({ fileName: OUT });
  if (SKILL_THEME) {
    const { applyTheme } = require(SKILL_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log("OK", OUT);
}

build().catch((error) => {
  console.error(error);
  process.exit(1);
});
