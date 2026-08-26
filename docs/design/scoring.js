// Rev4 subcontractor scoring engine — faithful port of "4. Bal Hesablaması" formulas
const R1 = x => Math.round(x * 10) / 10;
const SUB_CRITERIA = [
  // code, group, max, kind, spec
  ['A.1','A',5,'rubric',null,true],
  ['A.2','A',3,'bands',{zero:0,bands:[[3,1],[7,2]],top:3}],
  ['A.3','A',2,'rubric'],
  ['A.4','A',5,'rubric',null,true],
  ['B.1','B',8,'thresh',{cuts:[[500000,0],[1000000,.25],[5000000,.5],[10000000,.75]],top:1}],
  ['B.2','B',5,'thresh',{cuts:[[500000,0],[1000000,.3],[2500000,.6]],top:1}],
  ['B.3','B',3,'rubric'],
  ['B.4','B',4,'rubric'],
  ['C.1','C',9,'thresh',{cuts:[[2,0],[5,.3],[10,.7]],top:1}],
  ['C.2','C',7,'thresh',{cuts:[[1000000,0],[3000000,.4],[7000000,.75]],top:1}],
  ['C.3','C',4,'ongoing'],
  ['C.4','C',5,'rubric'],
  ['D.1','D',3,'rubric'],
  ['D.2','D',4,'rubric'],
  ['D.3','D',3,'rubric'],
  ['E.1','E',4,'thresh',{cuts:[[20,0],[50,.4],[100,.75]],top:1}],
  ['E.2','E',4,'thresh',{cuts:[[3,0],[8,.4],[16,.75]],top:1}],
  ['E.3','E',3,'rubric'],
  ['E.4','E',4,'rubric'],
  ['F.1','F',4,'rubric',null,true],
  ['F.2','F',3,'rubric'],
  ['F.3','F',3,'rubric'],
  ['G.1','G',3,'rubric'],
  ['G.2','G',2,'thresh',{cuts:[[1,0],[3,.4],[6,.7]],top:1}],
];
function scoreCriterion(def, v) {
  const [code, grp, max, kind, spec] = def; v = Number(v) || 0;
  switch (kind) {
    case 'rubric': return R1(v / 3 * max);
    case 'bands': { if (v === 0) return 0; for (const [lim, pts] of spec.bands) if (v <= lim) return pts; return spec.top; }
    case 'thresh': { for (const [lim, frac] of spec.cuts) if (v < lim) return R1(max * frac); return max; }
    case 'ongoing': return v === 0 ? R1(max * .25) : v <= 3 ? R1(max * .5) : v <= 6 ? max : R1(max * .75);
  }
}
function scoreSubcontractor(raw) {
  const per = {}, groups = { A: 0, B: 0, C: 0, D: 0, E: 0, F: 0, G: 0 };
  for (const d of SUB_CRITERIA) { const s = scoreCriterion(d, raw[d[0]]); per[d[0]] = s; groups[d[1]] = R1(groups[d[1]] + s); }
  const total = R1(Object.values(groups).reduce((a, b) => a + b, 0));
  const ko = SUB_CRITERIA.filter(d => d[5]).every(d => (Number(raw[d[0]]) || 0) > 0);
  const cls = !ko ? 'KO' : total >= 90 ? 'A' : total >= 80 ? 'B' : total >= 70 ? 'C' : total >= 60 ? 'D' : 'F';
  return { per, groups, total, ko, cls };
}
if (typeof module !== 'undefined') module.exports = { scoreSubcontractor, SUB_CRITERIA };
