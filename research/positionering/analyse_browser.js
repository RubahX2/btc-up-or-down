// Analyse volgens research/positionering/PLAN.md, in de browser (per beurs, eigen prijzen).
// Verwacht: window._D = {dates:[YYYY-MM-DD...], close:[...], fund:{date:dagsom}, oi:{date:oi_btc}|null}
const D = window._D, N = D.dates.length, END = '2026-10-29', P1E = '2022-12-31', P2S = '2023-01-01';
const c = D.close, idx = Object.fromEntries(D.dates.map((d,i)=>[d,i]));
const fundArr = D.dates.map(d => D.fund[d] ?? NaN);
const f7 = fundArr.map((_,i) => { if (i < 6) return NaN; let s=0; for (let k=i-6;k<=i;k++){ if (isNaN(fundArr[k])) return NaN; s+=fundArr[k]; } return s/7; });
const FUND = f7.map((v,i) => { if (isNaN(v)) return NaN; const h = f7.slice(0,i+1).filter(x=>!isNaN(x)); if (h.length < 180) return NaN; return h.filter(x=>x<v).length / h.length * 100; });
const oiArr = D.oi ? D.dates.map(d => D.oi[d] ?? NaN) : null;
const OI30 = oiArr ? oiArr.map((v,i) => i>=30 && !isNaN(v) && !isNaN(oiArr[i-30]) ? v/oiArr[i-30]-1 : NaN) : null;
const ret = c.map((v,i)=> i ? v/c[i-1]-1 : 0);
const sma = n => c.map((_,i)=> i<n-1 ? NaN : c.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n);
const S = [20,50,100,200].map(sma);
const cnt = c.map((v,i)=> S.filter(s=>v>s[i]).length + [14,30,60,90].filter(L=> i>=L && v>c[i-L]).length);
let start = FUND.findIndex(x=>!isNaN(x)); if (OI30) start = Math.max(start, OI30.findIndex(x=>!isNaN(x))); start = Math.max(start, 200);
const endI = idx[END] ?? N-1, p1e = D.dates.findIndex(d=>d>P1E)-1, p2s = p1e+1;
const out = {bron: D.bron, start: D.dates[start], eind: D.dates[endI], dagen: endI-start+1, prijs_eerste: D.dates[0]};
// Toets 1
const fwd_dd = c.map((v,i)=> i+30<N ? Math.min(...c.slice(i+1,i+31))/v-1 : NaN), fwd_r = c.map((v,i)=> i+30<N ? c[i+30]/v-1 : NaN);
const rank = a => { const s=a.map((v,i)=>[v,i]).sort((x,y)=>x[0]-y[0]); const r=new Array(a.length); s.forEach(([v,i],k)=>r[i]=k); return r; };
const spear = (x,y) => { const rx=rank(x), ry=rank(y), n=x.length, mx=(n-1)/2; let num=0,dx=0,dy=0; for(let i=0;i<n;i++){num+=(rx[i]-mx)*(ry[i]-mx);dx+=(rx[i]-mx)**2;dy+=(ry[i]-mx)**2;} return num/Math.sqrt(dx*dy); };
const t1 = {};
for (const [nm, f] of [['FUND', FUND], ['OI30', OI30]]) { if (!f) continue;
  const ii = []; for (let i=start;i<=endI;i++) if (!isNaN(f[i]) && !isNaN(fwd_dd[i])) ii.push(i);
  const fx = ii.map(i=>f[i]), dd = ii.map(i=>fwd_dd[i]), rr = ii.map(i=>fwd_r[i]);
  const order = ii.map((_,k)=>k).sort((a,b)=>fx[a]-fx[b]); const q = [];
  for (let k=0;k<5;k++){ const sel = order.slice(Math.floor(k*order.length/5), Math.floor((k+1)*order.length/5)); const m = a => sel.reduce((s,j)=>s+a[j],0)/sel.length;
    q.push([+m(fx).toFixed(2), +(m(dd)*100).toFixed(1), +(m(rr)*100).toFixed(1)]); }
  t1[nm] = {rho_daling: +spear(fx,dd).toFixed(3), rho_rendement: +spear(fx,rr).toFixed(3), n: ii.length, kwintielen_kenmerk_daling30_rend30: q}; }
out.toets1 = t1;
// simulatie C1b met regels
const FEE = 0.0007;
function run(a, b, noEntry, forceExit) { let pos=0, eq=1, armed=true, eqs=[], trades=[];
  for (let i=a;i<=b;i++){ if (i>a && pos) eq *= 1+ret[i]; const want = cnt[i] >= 6; if (!want) armed = true;
    if (pos) { const stop = forceExit ? forceExit(i) : false; if (!want || stop) { pos=0; eq*=1-FEE; trades[trades.length-1].push(c[i]); if (stop && want) armed=false; } }
    else if (want && armed && !(noEntry && noEntry(i))) { pos=1; eq*=1-FEE; trades.push([i, c[i]]); }
    eqs.push(eq); }
  const r = eqs.slice(1).map((v,k)=>v/eqs[k]-1), m = r.reduce((s,x)=>s+x,0)/r.length, sd = Math.sqrt(r.reduce((s,x)=>s+(x-m)**2,0)/(r.length-1));
  let pk=-1, dd=0; for (const v of eqs){ pk=Math.max(pk,v); dd=Math.min(dd, v/pk-1); }
  return {jaar: +((Math.pow(eqs[eqs.length-1], 365/eqs.length)-1)*100).toFixed(1), sharpe: +(m/sd*Math.sqrt(365)).toFixed(2), daling: +(dd*100).toFixed(1), trades}; }
// Toets 2
const all = run(start, endI).trades.filter(t=>t.length===3);
const mw = (x,y) => { const all_ = x.map(v=>[v,0]).concat(y.map(v=>[v,1])).sort((a,b)=>a[0]-b[0]); let R=0; all_.forEach(([v,g],k)=>{ if(g===0) R+=k+1; }); const n1=x.length,n2=y.length,U=R-n1*(n1+1)/2, mu=n1*n2/2, s=Math.sqrt(n1*n2*(n1+n2+1)/12), z=Math.abs(U-mu)/s; return +(2*(1-0.5*(1+erf(z/Math.SQRT2)))).toFixed(3); };
function erf(x){ const t=1/(1+0.3275911*x); return 1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x); }
const med = a => { const s=[...a].sort((x,y)=>x-y); return s.length ? +s[Math.floor(s.length/2)].toFixed(3) : null; };
const t2 = {n_trades: all.length};
for (const [nm, f] of [['FUND', FUND], ['OI30', OI30]]) { if (!f) continue;
  const w = all.filter(t=>t[2]/t[1]-1-2*FEE>0).map(t=>f[t[0]]).filter(v=>!isNaN(v)), l = all.filter(t=>t[2]/t[1]-1-2*FEE<=0).map(t=>f[t[0]]).filter(v=>!isNaN(v));
  t2[nm] = {winnaars_mediaan: med(w), n_w: w.length, verliezers_mediaan: med(l), n_l: l.length, p: mw(w,l)}; }
out.toets2 = t2;
// Toets 3
const base = [run(start,p1e), run(p2s,endI)];
const rules = {};
for (const p of [80,90,95]) rules['R1 geen instap FUND>p'+p] = [i=>FUND[i]>p, null];
for (const p of [80,90,95]) rules['R2 uit FUND>p'+p] = [null, i=>FUND[i]>p];
if (OI30) { for (const q of [0.2,0.3,0.5]) rules['R3 geen instap OI30>'+q] = [i=>OI30[i]>q, null];
  for (const q of [0.2,0.3]) rules['R4 uit FUND>p80 en OI30>'+q] = [null, i=>FUND[i]>80 && OI30[i]>q]; }
const strip = s => ({jaar: s.jaar, sharpe: s.sharpe, daling: s.daling});
const t3 = {C1b: [strip(base[0]), strip(base[1])]}, res = {};
for (const [k,[ne,fe]] of Object.entries(rules)) { const s=[run(start,p1e,ne,fe), run(p2s,endI,ne,fe)]; res[k]=s; t3[k] = [strip(s[0]), strip(s[1])]; }
out.toets3 = t3;
const verdict = {};
for (const fam of ['R1','R2','R3','R4']) { const ks = Object.keys(res).filter(k=>k.startsWith(fam)); if (!ks.length) continue;
  const best = ks.reduce((a,b)=> res[b][0].sharpe > res[a][0].sharpe ? b : a); const [s1,s2] = res[best];
  const ok = s1.sharpe >= base[0].sharpe+0.10 && s1.daling >= base[0].daling && s2.sharpe >= base[1].sharpe+0.10 && s2.daling >= base[1].daling;
  verdict[fam] = best + ' -> P2 Sharpe ' + s2.sharpe + ' vs ' + base[1].sharpe + ', daling ' + s2.daling + ' vs ' + base[1].daling + ': ' + (ok ? 'SLAAGT' : 'slaagt niet'); }
out.oordeel = verdict;
out
