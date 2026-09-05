const fs = require("fs");
const path = require("path");

const SOURCE =
  "<AUDIT_ROOT>/tavern-unpacked-1.2.0.10-fabric/data/kaleidoscope_tavern";
const TARGET =
  "<AUDIT_ROOT>/KaleidoscopeTavern-1.21.1/src/generated/resources/data/kaleidoscope_tavern";
const SOURCE_LANG =
  "<AUDIT_ROOT>/tavern-unpacked-1.2.0.10-fabric/assets/kaleidoscope_tavern/lang";
const TARGET_LANG =
  "<AUDIT_ROOT>/KaleidoscopeTavern-1.21.1/src/main/resources/assets/kaleidoscope_tavern/lang";

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(file) : entry.name.endsWith(".json") ? [file] : [];
  });
}

function normalizeIngredient(value) {
  if (typeof value === "string") {
    return value.startsWith("#") ? { tag: value.slice(1) } : { item: value };
  }
  return Array.isArray(value) ? value.map(normalizeIngredient) : value;
}

function normalizeRecipe(recipe) {
  const normalized = structuredClone(recipe);
  if (normalized.type === "minecraft:crafting_shaped" && normalized.key) {
    for (const key of Object.keys(normalized.key)) {
      normalized.key[key] = normalizeIngredient(normalized.key[key]);
    }
  }
  if (normalized.type === "minecraft:crafting_shapeless" && normalized.ingredients) {
    normalized.ingredients = normalized.ingredients.map(normalizeIngredient);
  }
  if (normalized.type === "kaleidoscope_tavern:barrel") {
    normalized.carrier = normalizeIngredient(normalized.carrier);
    if (normalized.ingredients) {
      normalized.ingredients = normalized.ingredients.map(normalizeIngredient);
    }
  }
  if (normalized.type === "kaleidoscope_tavern:pressing_tub") {
    normalized.ingredient = normalizeIngredient(normalized.ingredient);
  }
  if (normalized.type === "kaleidoscope_tavern:shaker") {
    normalized.ingredients = normalized.ingredients.map(normalizeIngredient);
  }
  return normalized;
}

function differences(source, target, jsonPath = "") {
  if (JSON.stringify(source) === JSON.stringify(target)) {
    return [];
  }
  if (
    source === null ||
    target === null ||
    typeof source !== "object" ||
    typeof target !== "object" ||
    Array.isArray(source) !== Array.isArray(target)
  ) {
    return [`${jsonPath}: ${JSON.stringify(source)} -> ${JSON.stringify(target)}`];
  }
  const keys = [...new Set([...Object.keys(source), ...Object.keys(target)])].sort();
  return keys.flatMap((key) => {
    const childPath = `${jsonPath}/${key}`;
    if (!(key in source)) {
      return [`${childPath}: <missing> -> ${JSON.stringify(target[key])}`];
    }
    if (!(key in target)) {
      return [`${childPath}: ${JSON.stringify(source[key])} -> <missing>`];
    }
    return differences(source[key], target[key], childPath);
  });
}

function compareRecipes() {
  const sourceRoot = path.join(SOURCE, "recipe");
  const targetRoot = path.join(TARGET, "recipe");
  const results = [];
  for (const sourceFile of walk(sourceRoot)) {
    const relative = path.relative(sourceRoot, sourceFile).replaceAll("\\", "/");
    const targetFile = path.join(targetRoot, relative);
    const source = normalizeRecipe(JSON.parse(fs.readFileSync(sourceFile, "utf8")));
    const target = normalizeRecipe(JSON.parse(fs.readFileSync(targetFile, "utf8")));
    const diff = differences(source, target);
    if (diff.length) {
      results.push({ relative, diff });
    }
  }
  console.log(`recipe semantic differences: ${results.length}`);
  for (const result of results) {
    console.log(`[${result.relative}]`);
    for (const diff of result.diff) {
      console.log(`  ${diff}`);
    }
  }
}

compareRecipes();

function counterpartKey(key) {
  if (key.startsWith("item.kaleidoscope_tavern.")) {
    return key.replace("item.kaleidoscope_tavern.", "block.kaleidoscope_tavern.");
  }
  if (key.startsWith("block.kaleidoscope_tavern.")) {
    return key.replace("block.kaleidoscope_tavern.", "item.kaleidoscope_tavern.");
  }
  return null;
}

function compareLanguages() {
  console.log("language comparison:");
  const sourceEnglish = JSON.parse(fs.readFileSync(path.join(SOURCE_LANG, "en_us.json"), "utf8"));
  const targetEnglish = JSON.parse(fs.readFileSync(path.join(TARGET_LANG, "en_us.json"), "utf8"));
  for (const file of fs.readdirSync(SOURCE_LANG).filter((name) => name.endsWith(".json")).sort()) {
    const source = JSON.parse(fs.readFileSync(path.join(SOURCE_LANG, file), "utf8"));
    const target = JSON.parse(fs.readFileSync(path.join(TARGET_LANG, file), "utf8"));
    const shared = Object.keys(source).filter((key) => key in target);
    const differentValues = shared.filter((key) => source[key] !== target[key]);
    const sourceOnly = Object.keys(source).filter((key) => !(key in target));
    const aliasPresent = sourceOnly.filter((key) => {
      const counterpart = counterpartKey(key);
      return counterpart && counterpart in target;
    });
    const aliasEquivalent = aliasPresent.filter((key) => {
      const counterpart = counterpartKey(key);
      return source[key] === target[counterpart];
    });
    const trueMissing = sourceOnly.filter((key) => !aliasPresent.includes(key));
    const targetOnly = Object.keys(target).filter((key) => !(key in source));
    console.log(
      `[${file}] source=${Object.keys(source).length} target=${Object.keys(target).length} ` +
        `shared=${shared.length} shared-value-diff=${differentValues.length} ` +
        `source-only=${sourceOnly.length} alias-present=${aliasPresent.length} ` +
        `alias-value-equal=${aliasEquivalent.length} ` +
        `true-missing=${trueMissing.length} target-only=${targetOnly.length}`,
    );
    if (trueMissing.length) {
      console.log("  true missing:");
      for (const key of trueMissing) {
        console.log(`    ${key} = ${JSON.stringify(source[key])}`);
      }
    }
    if (differentValues.length) {
      console.log("  changed shared values:");
      for (const key of differentValues) {
        console.log(`    ${key}: ${JSON.stringify(source[key])} -> ${JSON.stringify(target[key])}`);
      }
    }

    const sourceEffective = { ...sourceEnglish, ...source };
    const targetEffective = { ...targetEnglish, ...target };
    const effectiveMissing = [];
    const effectiveDifferent = [];
    for (const [key, value] of Object.entries(sourceEffective)) {
      let targetKey = key;
      if (!(targetKey in targetEffective)) {
        const counterpart = counterpartKey(key);
        if (counterpart && counterpart in targetEffective) {
          targetKey = counterpart;
        }
      }
      if (!(targetKey in targetEffective)) {
        effectiveMissing.push(key);
      } else if (targetEffective[targetKey] !== value) {
        effectiveDifferent.push({ key, source: value, target: targetEffective[targetKey] });
      }
    }
    console.log(
      `  effective-with-en-fallback: source=${Object.keys(sourceEffective).length} ` +
        `target=${Object.keys(targetEffective).length} missing=${effectiveMissing.length} ` +
        `value-different=${effectiveDifferent.length}`,
    );
    if (effectiveMissing.length) {
      console.log(`    effective missing keys: ${effectiveMissing.join(", ")}`);
    }
    if (effectiveDifferent.length) {
      console.log("    effective changed values:");
      for (const entry of effectiveDifferent) {
        console.log(`      ${entry.key}: ${JSON.stringify(entry.source)} -> ${JSON.stringify(entry.target)}`);
      }
    }
  }
}

compareLanguages();
