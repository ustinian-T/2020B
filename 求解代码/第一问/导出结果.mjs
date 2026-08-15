import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "file:///C:/Users/ustinian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";


const projectRoot = process.cwd();
const templatePath = path.join(projectRoot, "数据", "Result.xlsx");
const outputDir = path.join(projectRoot, "求解代码", "第一问", "结果输出");
const outputPath = path.join(outputDir, "Result_已填写.xlsx");
const qaDir = path.join(projectRoot, "._qa", "result-xlsx");
const summaryPath = path.join(outputDir, "求解摘要.json");

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(qaDir, { recursive: true });

const input = await FileBlob.load(templatePath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItemAt(0);

const before = await workbook.inspect({
  kind: "region",
  sheetId: sheet.name,
  range: "A1:K34",
  maxChars: 3000,
});
console.log("TEMPLATE_INSPECT", before.ndjson);
const beforePreview = await workbook.render({
  sheetName: sheet.name,
  range: "A1:K34",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(
  path.join(qaDir, "template-before.png"),
  new Uint8Array(await beforePreview.arrayBuffer()),
);

const summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));

function resultRows(levelName) {
  const result = summary["关卡结果"][levelName];
  const initial = result["初始采购"];
  const firstRecord = result["逐日策略"][0];
  const initialCash =
    summary["公共参数"]["初始资金"] - 5 * initial.water - 10 * initial.food;
  const rows = [[firstRecord.from_node, initialCash, initial.water, initial.food]];
  for (const record of result["逐日策略"]) {
    rows.push([record.to_node, record.cash, record.water, record.food]);
  }
  while (rows.length < 31) rows.push([null, null, null, null]);
  return rows.slice(0, 31);
}

sheet.getRange("B4:E34").values = resultRows("第一关");
sheet.getRange("H4:K34").values = resultRows("第二关");

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const check = await workbook.inspect({
  kind: "region",
  sheetId: sheet.name,
  range: "A1:K34",
  maxChars: 8000,
  tableMaxRows: 34,
  tableMaxCols: 11,
});
console.log("FINAL_INSPECT", check.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log("FORMULA_ERRORS", errors.ndjson);

const finalPreview = await workbook.render({
  sheetName: sheet.name,
  range: "A1:K34",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(
  path.join(qaDir, "result-final.png"),
  new Uint8Array(await finalPreview.arrayBuffer()),
);

console.log(outputPath);
