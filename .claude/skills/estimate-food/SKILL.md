---
name: estimate-food
description: Estimate kcal, carbs, protein and fat for meals in the Fuel food log (nutrition/intake/*.json) that have no numbers yet, and give a short verdict on the day's intake. Use when the user asks to "estimate my food log", "how much did I eat", or in the evening scheduled run.
---

# Estimate the food log

Work from the project root (the folder with CLAUDE.md).

## 1. Find meals to estimate
Files: `nutrition/intake/<YYYY-MM-DD>.json`, each `{"meals": [{id, slot, time, text, kcal, carbs, protein, fat, source}]}`.
Look at the last 7 days. A meal needs an estimate when `kcal` is null. Leave meals with `source: "you"` untouched
(the user entered those numbers). Nothing to estimate → say so and go to step 4.

## 2. Estimate
First check `nutrition/recipes.yaml`: when a meal names one of those recipes, use its `per_serving` values
(scaled to the portion described). When the user gives a new recipe with amounts, add it there.
For each meal, estimate kcal, carbs, protein and fat (grams) from the description. The text may be Dutch.
- Use typical Dutch portions unless the text gives amounts: slice of bread 35 g (wholemeal ~85 kcal, 14 g carbs, 3.5 g protein),
  tablespoon of peanut butter 15 g, a bowl of oats 60 g dry, a plate of pasta 90 g dry, rice 75 g dry, a banana 120 g,
  glass of milk 200 ml, a cup of yoghurt or quark 150 g, cheese on bread 20 g per slice, a hand of nuts 25 g.
- Use Dutch food-composition values (NEVO) where you know them; otherwise standard values.
- Cooking fat: fish, meat, eggs or vegetables that are baked or fried (gebakken) get ~5 g oil or butter per portion
  as a separate item ("Olie om in te bakken", ~5 g), unless the user says otherwise; airfryer/oven/boiled food gets none.
- When the text is vague ("pasta with sauce"), pick a middle portion and write it so the user can correct it.
- Round kcal to 10 and grams to whole numbers. Check: 4·carbs + 4·protein + 9·fat ≈ kcal (within ~10 %).

Write the numbers back into the same meal in the JSON file, with a breakdown per ingredient so the user can see how
the estimate was made (the Fuel page shows it when the meal is clicked):
`"items": [{"name": "Havermout", "amount": "40 g", "kcal": 150, "carbs": 24, "protein": 5, "fat": 3}, …]`,
prefix guessed amounts with `~`. The meal's kcal/carbs/protein/fat must equal the sum of its items. Also set
`"source": "estimate"` and `"assumed": "<one short line on what you assumed>"`. Keep every other field and meal as it is.
When the user corrects an amount, update that item and the meal totals.
Only write inside `nutrition/intake/`.

## 3. Check the day
Get the day's verdict with `curl -s localhost:8765/api/fuel/day/<date>` (or `.venv/bin/python -c` with
`app.backend.nutrition.day("<date>")` if the dashboard isn't running). It gives totals, targets (carbs g/kg for that
day's training, protein 1.6–2.0 g/kg) and energy availability (EA: kcal eaten minus training kcal, per kg fat-free mass).

## 4. Reply
Per day estimated: the totals and one line on what stands out, e.g. "Carbs 3.9 g/kg on a 2.5 h day (target 6–8):
add a carb-rich snack before and after long rides." Mention EA only when every meal of the day has numbers:
45+ is fine, 30–45 is low if it lasts, under 30 is too low. Keep it practical and non-judgemental; never comment on
body weight or shape. If EA stays under 30 for several days, suggest talking to a sports dietitian.
