export type Institution={id:string;name:string;category:string;jurisdiction:string;city:string;role:string;source:string;sourceLabel:string;confidence:number;freshness:string}
export const institutions:Institution[]=[
 {id:'sequoia',name:'Sequoia Capital',category:'Venture Capital',jurisdiction:'United States',city:'Menlo Park',role:'Company formation and growth capital',source:'https://sequoiacap.com/',sourceLabel:'Official website',confidence:96,freshness:'Retrieved Aug 2026'},
 {id:'a16z',name:'Andreessen Horowitz',category:'Venture Capital',jurisdiction:'United States',city:'Menlo Park',role:'Venture and growth investing',source:'https://a16z.com/',sourceLabel:'Official website',confidence:95,freshness:'Retrieved Aug 2026'},
 {id:'index',name:'Index Ventures',category:'Venture Capital',jurisdiction:'United Kingdom',city:'London',role:'Global venture investing',source:'https://www.indexventures.com/',sourceLabel:'Official website',confidence:95,freshness:'Retrieved Aug 2026'},
 {id:'blackstone',name:'Blackstone',category:'Private Equity',jurisdiction:'United States',city:'New York',role:'Alternative asset management',source:'https://www.blackstone.com/',sourceLabel:'Official website',confidence:97,freshness:'Retrieved Aug 2026'},
 {id:'kkr',name:'KKR',category:'Private Equity',jurisdiction:'United States',city:'New York',role:'Private markets investment',source:'https://www.kkr.com/',sourceLabel:'Official website',confidence:97,freshness:'Retrieved Aug 2026'},
 {id:'apollo',name:'Apollo Global Management',category:'Private Equity',jurisdiction:'United States',city:'New York',role:'Alternative asset management',source:'https://www.apollo.com/',sourceLabel:'Official website',confidence:96,freshness:'Retrieved Aug 2026'},
 {id:'bridgewater',name:'Bridgewater Associates',category:'Hedge Fund',jurisdiction:'United States',city:'Westport',role:'Global macro investment management',source:'https://www.bridgewater.com/',sourceLabel:'Official website',confidence:98,freshness:'Retrieved Aug 2026'},
 {id:'aqr',name:'AQR Capital Management',category:'Hedge Fund',jurisdiction:'United States',city:'Greenwich',role:'Systematic investment management',source:'https://www.aqr.com/',sourceLabel:'Official website',confidence:95,freshness:'Retrieved Aug 2026'},
 {id:'gic',name:'GIC',category:'Sovereign Wealth',jurisdiction:'Singapore',city:'Singapore',role:'Long-term global investor',source:'https://www.gic.com.sg/',sourceLabel:'Official website',confidence:98,freshness:'Retrieved Aug 2026'},
 {id:'adia',name:'Abu Dhabi Investment Authority',category:'Sovereign Wealth',jurisdiction:'United Arab Emirates',city:'Abu Dhabi',role:'Global diversified investment institution',source:'https://www.adia.ae/',sourceLabel:'Official website',confidence:98,freshness:'Retrieved Aug 2026'},
 {id:'temasek',name:'Temasek',category:'Sovereign Wealth',jurisdiction:'Singapore',city:'Singapore',role:'Global investment company',source:'https://www.temasek.com.sg/',sourceLabel:'Official website',confidence:98,freshness:'Retrieved Aug 2026'},
 {id:'gv',name:'GV',category:'Corporate Venture Capital',jurisdiction:'United States',city:'San Francisco',role:'Independent venture capital firm backed by Alphabet',source:'https://www.gv.com/about',sourceLabel:'Official about page',confidence:98,freshness:'Retrieved Aug 2026'},
 {id:'intel',name:'Intel Capital',category:'Corporate Venture Capital',jurisdiction:'United States',city:'Santa Clara',role:'Strategic technology investing',source:'https://www.intelcapital.com/',sourceLabel:'Official website',confidence:95,freshness:'Retrieved Aug 2026'},
 {id:'m12',name:'M12',category:'Corporate Venture Capital',jurisdiction:'United States',city:'Redmond',role:'Microsoft venture fund',source:'https://m12.vc/',sourceLabel:'Official website',confidence:95,freshness:'Retrieved Aug 2026'},
 {id:'cpp',name:'CPP Investments',category:'Pension',jurisdiction:'Canada',city:'Toronto',role:'Global pension investment management',source:'https://www.cppinvestments.com/',sourceLabel:'Official website',confidence:98,freshness:'Retrieved Aug 2026'},
 {id:'ubs',name:'UBS Global Wealth Management',category:'Private Bank',jurisdiction:'Switzerland',city:'Zurich',role:'Global wealth management',source:'https://www.ubs.com/',sourceLabel:'Official website',confidence:97,freshness:'Retrieved Aug 2026'}
]
export const ranking=[
 {id:'northstar',name:'Northstar Collection',region:'Zurich · Europe',fit:94,status:'Qualified',factors:[['Collection fit',98],['Acquisition mandate',94],['Relationship path',91],['Evidence confidence',96],['Contactability',88]]},
 {id:'aster',name:'Aster Family Office',region:'Singapore · APAC',fit:89,status:'Review',factors:[['Collection fit',91],['Acquisition mandate',95],['Relationship path',76],['Evidence confidence',90],['Contactability',82]]},
 {id:'meridian',name:'Meridian Arts Trust',region:'New York · Americas',fit:84,status:'Qualified',factors:[['Collection fit',88],['Acquisition mandate',80],['Relationship path',84],['Evidence confidence',92],['Contactability',74]]}
]
export const evidence=[
 {id:'authority',title:'Authority to sell',state:'SUPPORTED',confidence:96,freshness:'2 days',source:'Synthetic signed authority',decision:'Specialist accepted',conflict:'None'},
 {id:'provenance',title:'Provenance chain 1988–2026',state:'PASS — EXCEPTIONS',confidence:87,freshness:'4 days',source:'Synthetic invoices and exhibition record',decision:'Original 1998 invoice requested',conflict:'Scan/original mismatch'},
 {id:'attribution',title:'Attribution and catalogue reference',state:'VERIFIED',confidence:98,freshness:'1 day',source:'Synthetic catalogue raisonné reference',decision:'Specialist accepted',conflict:'None'},
 {id:'restitution',title:'Restitution review',state:'HUMAN REVIEW',confidence:71,freshness:'Today',source:'Synthetic ownership and loss-register checks',decision:'Counsel escalation open',conflict:'1939–1946 custody gap'},
 {id:'export',title:'Export and cultural property',state:'SUPPORTED',confidence:92,freshness:'Today',source:'Synthetic jurisdiction assessment',decision:'No current restriction identified',conflict:'None'}
]
export const graphNodes=[
 {id:'asset',type:'ASSET',name:'Untitled, 1988',detail:'Synthetic artwork · evidence 87%'},
 {id:'consignor',type:'CONSIGNOR',name:'Arden Holdings',detail:'Synthetic entity · authority supported'},
 {id:'advisor',type:'ADVISOR',name:'Claremont Art',detail:'Synthetic adviser · mandate supported'},
 {id:'collector',type:'COLLECTOR',name:'Northstar Collection',detail:'Synthetic collector · fit 94'},
 {id:'capital',type:'CAPITAL CONTEXT',name:'GIC',detail:'Real institution · public identity only'}
]
export const searchItems=[
 {type:'Asset',name:'Untitled, 1988',meta:'Synthetic private-sale asset',href:'/deal-room'},
 {type:'Opportunity',name:'PM-2026-014',meta:'Synthetic discreet private sale',href:'/deal-room'},
 ...institutions.map(x=>({type:x.category,name:x.name,meta:`${x.city} · ${x.jurisdiction}`,href:'/universes'}))
]
