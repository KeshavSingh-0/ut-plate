// J2 Plate — targets and portion optimizer. No DOM code here, so it can be tested in Node.
(function (root) {
  // Column order matches the Food sheet: Cals Fat-T Fat-S TFA Chol Sod Carb Fiber Sugar SugAdd Prot D Calc Iron Potas
  const KEYS = ["cal", "fat", "sfa", "tfa", "chol", "sod", "carb", "fib", "sug", "add", "pro", "vitd", "calc", "iron", "pot"];
  const LABELS = ["Calories", "Fat", "Sat fat", "Trans fat", "Cholesterol", "Sodium", "Carbs", "Fiber", "Sugar",
    "Added sugar", "Protein", "Vitamin D", "Calcium", "Iron", "Potassium"];
  const UNITS = ["kcal", "g", "g", "g", "mg", "mg", "g", "g", "g", "g", "g", "mcg", "mg", "mg", "mg"];
  // aim = hit it; max = stay under; min = reach at least
  const KIND = ["aim", "aim", "max", "max", "max", "max", "aim", "min", "max", "max", "min", "min", "min", "min", "min"];
  // how much each miss hurts (squared, relative to the target)
  const WEIGHT = [14, 3, 6, 0, 1.5, 3, 2, 3, 1, 5, 16, 0.2, 0.6, 0.8, 0.6];

  const PLAN_A = [2600, 80, 20, 0, 200, 2300, 330, 35, 60, 25, 140, 20, 1000, 14, 3400]; // weeks 1–2 and 9
  const PLAN_B = [2350, 72, 18, 0, 200, 2300, 280, 38, 55, 20, 145, 20, 1000, 14, 3400]; // weeks 3–8, 10–12

  function planWeek(dateISO, startISO) {
    const d = (Date.parse(dateISO) - Date.parse(startISO)) / 864e5;
    return Math.floor(d / 7) + 1;
  }
  function dailyTarget(dateISO, startISO) {
    const w = planWeek(dateISO, startISO);
    return (w === 1 || w === 2 || w === 9) ? PLAN_A.slice() : PLAN_B.slice();
  }

  const zero = () => KEYS.map(() => 0);
  function addInto(acc, n, q) { for (let i = 0; i < acc.length; i++) acc[i] += (n[i] || 0) * q; return acc; }
  function sumPlate(plate, items) {
    const t = zero();
    for (const p of plate) if (items[p.id]) addInto(t, items[p.id].n, p.qty);
    return t;
  }

  function cost(tot, tgt) {
    let c = 0;
    for (let i = 0; i < KEYS.length; i++) {
      const T = tgt[i], v = tot[i];
      if (KIND[i] === "max") {
        if (i === 3) { c += 4 * v; continue; }          // trans fat: any is bad
        if (T <= 0) { c += WEIGHT[i] * v / 10; continue; }
        if (v > T) c += WEIGHT[i] * ((v - T) / T) ** 2;
      } else if (KIND[i] === "min") {
        if (T > 0 && v < T) c += WEIGHT[i] * ((T - v) / T) ** 2;
        else if (i === 10 && T > 0) c += 0.5 * ((v - T) / T) ** 2; // a little protein overshoot is fine
      } else if (T > 0) {
        c += WEIGHT[i] * ((v - T) / T) ** 2;
      }
    }
    return c;
  }

  // Pick whole portions from `cands` (array of {id, n, cap, bias}) to land as close to `tgt` as possible.
  function optimize(cands, tgt, opts = {}) {
    const maxDistinct = opts.maxDistinct || 6;
    const qty = new Map();
    const tot = zero();
    const total = () => {
      let distinct = 0, servings = 0, bias = 0;
      for (const [id, q] of qty) if (q > 0) { distinct++; servings += q; bias += cands[idx[id]].bias * q; }
      return { distinct, servings, bias };
    };
    const idx = {}; cands.forEach((c, i) => { idx[c.id] = i; });
    const floor = c => c.min || 0;
    const score = () => {
      const s = total();
      return cost(tot, tgt) + 0.04 * Math.max(0, s.distinct - 3) + 0.004 * s.servings + s.bias
        + (s.distinct > maxDistinct ? 1 : 0);
    };
    const apply = (c, d) => { qty.set(c.id, (qty.get(c.id) || 0) + d); addInto(tot, c.n, d); };
    for (const c of cands) if (floor(c) > 0) apply(c, floor(c));   // the user's own starter dishes stay as chosen
    let best = score();

    for (let iter = 0; iter < 200; iter++) {
      let move = null, moveScore = best;
      for (const c of cands) {
        const q = qty.get(c.id) || 0;
        if (q < c.cap) { apply(c, 1); const s = score(); if (s < moveScore - 1e-9) { moveScore = s; move = [[c, 1]]; } apply(c, -1); }
        if (q > floor(c)) { apply(c, -1); const s = score(); if (s < moveScore - 1e-9) { moveScore = s; move = [[c, -1]]; } apply(c, 1); }
      }
      if (!move) {   // try swapping one portion of a chosen item for another item
        for (const a of cands) {
          if (!(qty.get(a.id) > floor(a))) continue;
          apply(a, -1);
          for (const b of cands) {
            if (b === a || (qty.get(b.id) || 0) >= b.cap) continue;
            apply(b, 1); const s = score(); if (s < moveScore - 1e-9) { moveScore = s; move = [[a, -1], [b, 1]]; } apply(b, -1);
          }
          apply(a, 1);
        }
      }
      if (!move) break;
      for (const [c, d] of move) apply(c, d);
      best = moveScore;
    }
    const plate = [];
    for (const c of cands) { const q = qty.get(c.id) || 0; if (q > 0) plate.push({ id: c.id, qty: q }); }
    return { plate, total: tot.slice(), score: best };
  }

  // Simple seeded random so "Swap" gives repeatable alternatives.
  function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

  // Dishes the planner may use. `opts.starter` ({id: qty}) holds the user's own picks: they are kept exactly as
  // chosen and the rest of the plate is filled in around them. `opts.ban` ids are never suggested.
  function eligible(it, id, opts) {
    const icons = it.icons || [];
    if (!it.dessert && !icons.includes("veggie") && !icons.includes("vegan")) return false;
    if (opts.noEggs && icons.includes("eggs")) return false;
    if (opts.hidden && opts.hidden.has(id)) return false;
    if (opts.ban && opts.ban.has(id)) return false;
    return !!(it.n && it.n[0] > 0);
  }
  function candidates(menuEntries, items, opts) {
    opts = opts || {};
    const seen = new Set(), out = [];
    const r = rng(opts.seed || 1);
    const starter = opts.starter || {};
    const mk = (id, it, locked) => {
      const avoid = opts.avoid && opts.avoid.has(id) ? 0.05 : 0;
      const sweet = it.dessert ? 0.15 : 0;           // desserts are allowed, but rarely auto-picked
      const cap = it.n[0] < 60 ? 4 : 3;
      return { id, n: it.n, cap: locked ? starter[id] : cap, min: locked ? starter[id] : 0,
        bias: locked ? 0 : (opts.seed > 1 ? r() * 0.06 : 0) + avoid + sweet };
    };
    for (const e of menuEntries) {
      const it = items[e.id];
      if (!it || seen.has(e.id)) continue;
      seen.add(e.id);
      if (starter[e.id] > 0) { out.push(mk(e.id, it, true)); continue; }
      if (eligible(it, e.id, opts)) out.push(mk(e.id, it, false));
    }
    for (const id of Object.keys(starter))                 // starter dishes that aren't on this hall's menu keep their place
      if (!seen.has(id) && starter[id] > 0 && items[id]) out.push(mk(id, items[id], true));
    return out;
  }

  // Split what's left of the day across the meals still to eat.
  function mealTargets(dayTarget, alreadyEaten, mealsLeft, shares) {
    const remaining = dayTarget.map((t, i) => Math.max(0, t - alreadyEaten[i]));
    const totalShare = mealsLeft.reduce((s, m) => s + (shares[m] || 0), 0) || 1;
    const out = {};
    for (const m of mealsLeft) out[m] = remaining.map(v => v * (shares[m] || 0) / totalShare);
    return out;
  }

  const api = { eligible, KEYS, LABELS, UNITS, KIND, PLAN_A, PLAN_B, planWeek, dailyTarget, sumPlate, addInto, zero,
    cost, optimize, candidates, mealTargets };
  if (typeof module !== "undefined") module.exports = api; else root.Planner = api;
})(this);
