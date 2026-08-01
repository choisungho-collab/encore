/* ENCORE 코치 엔진 — match.html · player.html 공용 */
const COACH_SUPPLY={"Zergling":.5,"Hydralisk":1,"Mutalisk":2,"Lurker":2,"Scourge":.5,"Ultralisk":4,"Defiler":2,"Queen":2,"Guardian":2,"Devourer":2,"Drone":1,"Marine":1,"Firebat":1,"Medic":1,"Ghost":1,"SCV":1,"Vulture":2,"Siege Tank (Tank Mode)":2,"Siege Tank (Siege Mode)":2,"Goliath":2,"Wraith":2,"Valkyrie":3,"Dropship":2,"Science Vessel":2,"Battlecruiser":6,"Zealot":2,"Dragoon":2,"High Templar":2,"Dark Templar":2,"Archon":4,"Dark Archon":4,"Reaver":4,"Shuttle":2,"Observer":1,"Scout":3,"Corsair":2,"Carrier":6,"Arbiter":4,"Probe":1};
const COACH_WORKERS=new Set(["SCV","Drone","Probe"]);
const COACH_GAS=new Set(["Refinery","Assimilator","Extractor"]);
const COACH_PROD={"T":new Set(["Barracks","Factory","Starport"]),"P":new Set(["Gateway","Robotics Facility","Stargate"]),"Z":new Set(["Hatchery","Lair","Hive"])};
const COACH_WIN_TECH={"Z":{"Defiler":"디파일러","Lurker":"러커","Ultralisk":"울트라","Guardian":"가디언"},"T":{"Science Vessel":"사이언스베슬","Siege Tank (Tank Mode)":"시즈탱크","Battlecruiser":"배틀크루저"},"P":{"High Templar":"하이템플러","Archon":"아콘","Reaver":"리버","Arbiter":"아비터","Carrier":"캐리어"}};
const COACH_UKR={"Marine":"마린","Firebat":"파벳","Medic":"메딕","Vulture":"벌처","Goliath":"골리앗","Wraith":"레이스","Dropship":"드랍십","Science Vessel":"베슬","Valkyrie":"발키리","Battlecruiser":"배틀","Ghost":"고스트","Siege Tank (Tank Mode)":"탱크","Siege Tank (Siege Mode)":"탱크","Zealot":"질럿","Dragoon":"드라군","High Templar":"하템","Dark Templar":"다크","Archon":"아콘","Reaver":"리버","Corsair":"커세어","Carrier":"캐리어","Arbiter":"아비터","Scout":"스카웃","Shuttle":"셔틀","Zergling":"저글링","Hydralisk":"히드라","Mutalisk":"뮤탈","Lurker":"러커","Ultralisk":"울트라","Defiler":"디파일러","Guardian":"가디언","Devourer":"디바우러","Scourge":"스컬지","Queen":"퀸"};
const COACH_RACEKR={"T":"테란","P":"토스","Z":"저그","R":"랜덤"};
function pyRound(x){const f=Math.floor(x),d=x-f;if(d<0.5)return f;if(d>0.5)return f+1;return (f%2===0)?f:f+1;}
function _coach_race(r,unames){
  r=(r||"").toLowerCase();
  if(r.indexOf("toss")>=0||r.indexOf("prot")>=0)return "P";
  if(r.indexOf("zerg")>=0)return "Z";
  if(r.indexOf("terr")>=0)return "T";
  if(r==="p"||r==="pro")return "P";
  if(r==="z"||r==="zer")return "Z";
  if(r==="t"||r==="ter")return "T";
  if(unames&&unames.length){const n=new Set(unames);const hit=a=>a.some(x=>n.has(x));
    if(hit(["SCV","Marine","Vulture","Goliath","Wraith","Siege Tank (Tank Mode)","Siege Tank"]))return "T";
    if(hit(["Probe","Zealot","Dragoon","Dark Templar","Carrier","Corsair"]))return "P";
    if(hit(["Drone","Zergling","Hydralisk","Mutalisk","Lurker"]))return "Z";}
  return "T";
}
function _coach_first(build,names){for(const b of build){if(names.has(b.name))return b.t;}return null;}
function _s2(s){var q=(""+(s||"0:0")).split(":");return (+q[0])*60+(+q[1]||0);}
function _mmss(s){s=Math.max(0,Math.round(s||0));return Math.floor(s/60)+":"+("0"+(s%60)).slice(-2);}
function prodTarget(race,mins,maxSup){
  var t;
  if(mins<4)       t={T:2,P:2,Z:2}[race];   // 초반전: 3분대 게임에 해처리 4개 기준은 난센스
  else if(mins<5)  t={T:3,P:3,Z:3}[race];
  else if(mins<7)  t={T:5,P:6,Z:6}[race];
  else if(mins<9)  t={T:7,P:8,Z:8}[race];
  else if(mins<13) t={T:9,P:10,Z:10}[race];
  else             t={T:11,P:12,Z:11}[race];
  if(maxSup>=160)  t=Math.max(t,{T:9,P:9,Z:9}[race]);
  return t||4;
}
function coach_player(p,peers,mins,fast){
  mins=mins||0;
  // 게임 단계: 0 초반전(<6분) · 1 단기(<10) · 2 중기(<15) · 3 장기 — 단계별로 요구하는 게 다르다
  var ph=mins<6?0:(mins<10?1:(mins<15?2:3));
  var unames=(p.units||[]).map(function(u){return u.name;});
  var race=_coach_race(p.race,unames);var build=p.build||[];
  var units={};(p.units||[]).forEach(function(u){units[u.name]=u;});
  var bnames=new Set(build.map(function(b){return b.name;}));
  var pts=[];
  var T=function(tone,k,ti,tx,sec){pts.push(sec!=null?{tone:tone,k:k,t:ti,x:tx,sec:sec}:{tone:tone,k:k,t:ti,x:tx});};
  var gas=_coach_first(build,COACH_GAS);
  var prodN=(p.main_prod_n!=null)?p.main_prod_n:build.filter(function(b){return COACH_PROD[race].has(b.name);}).length;
  var prodKo=p.main_prod_ko||({T:"배럭",P:"게이트",Z:"해처리"}[race]||"생산건물");
  var ups=build.filter(function(b){return b.cat==="upgrade"||b.cat==="tech";});var up_n=ups.length;var up1=ups.length?ups[0].t:null;var upsec=up1?_s2(up1):null;
  var exp=(p.townhalls&&p.townhalls.length)?p.townhalls[0].t:null;
  var maxSup=p.max_supply||0;var tc=(p.townhalls||[]).length;
  var workers=0;Object.keys(units).forEach(function(n){if(COACH_WORKERS.has(n))workers+=units[n].n;});
  var army=0;Object.keys(units).forEach(function(n){if(!COACH_WORKERS.has(n))army+=units[n].n*(COACH_SUPPLY[n]||1);});
  var marine=(units["Marine"]||{}).n||0,medic=(units["Medic"]||{}).n||0,fbat=(units["Firebat"]||{}).n||0;
  var enemyP=(peers||[]).filter(function(pe){return pe&&pe.team!=null&&p.team!=null&&pe.team!==p.team&&pe.race==="P";}).length;
  var A=p.atk_lv||0,R=p.arm_lv||0,mxlv=Math.max(A,R),haslv=(p.atk_lv!=null||p.arm_lv!=null);
  var apm=p.apm,eapm=p.eapm,series=p.apm_series||[0];
  var wt=COACH_WIN_TECH[race];var have_wt=Object.keys(wt).filter(function(n){return units[n];}).map(function(n){return wt[n];});
  var raceKr=COACH_RACEKR[race];
  var timings={gas:gas,prod:prodN,up_n:up_n,up1:up1,exp:exp,army:pyRound(army),workers:workers,max_supply:p.max_supply,supply200:p.supply200,total_supply:p.total_supply,tcount:tc,atk_lv:p.atk_lv,arm_lv:p.arm_lv,supply_bld:p.supply_bld,supply_ko:p.supply_ko,main_prod_n:p.main_prod_n,main_prod_ko:p.main_prod_ko,scout_first:p.scout_first,scouted:p.scouted,atk_first:p.atk_first,groups:p.groups,drops:p.drops,prod_max_gap:p.prod_max_gap,prod_active:p.prod_active};

  // 1. 생산기지·리맥스 (최우선)
  var tgt=prodTarget(race,mins,maxSup);
  if(ph===0){
    if(prodN>=tgt) T("good","prod",prodKo+" "+prodN+"개 — 초반전 기준 충분","~"+Math.round(mins)+"분 게임엔 이 정도가 정석 — 생산 수보다 빌드·타이밍이 승부였어.");
    else if(prodN<2&&mins>=3.5) T("tip","prod",prodKo+" "+prodN+"개","초반전이라도 "+prodKo+" 2개는 있어야 러시를 받아치는 물량이 나와.");
  }else if(prodN>=tgt){
    T("good","prod",prodKo+" "+prodN+"개 — 생산·리맥스 탄탄","권장 "+tgt+"개 이상 — 병력이 갈려도 바로 리맥스되는 구조야.");
  }else if(prodN<Math.max(2,tgt*0.6)){
    T("warn","prod",prodKo+" "+prodN+"개 — 생산기지 부족","기준 "+tgt+"개인데 "+prodN+"개 — 리맥스가 느려 한타 한 번에 무너져. 돈 남기 전에 "+prodKo+"부터.");
  }else{
    T("tip","prod",prodKo+" "+prodN+"개 — 조금 부족","권장 "+tgt+"개에 살짝 부족 — 2~3개만 더 지으면 리맥스가 확 빨라져.");
  }

  // 2. 업그레이드
  var usyn="";
  if(units["Goliath"]&&mxlv<2) usyn=" 골리앗은 공2업이 생명.";
  else if(units["Marine"]&&mxlv===0) usyn=" 마린은 공1업만 돼도 확 달라져.";
  else if(race==="Z"&&(units["Hydralisk"]||units["Zergling"])&&mxlv<2) usyn=" 다수 유닛엔 공업 한 단계가 곱으로 들어가.";
  if(mins>=7){
    if(haslv){
      var ut="업그레이드 공"+A+"·방"+R;
      if(mxlv===0)      T("warn","up",ut,"노업은 치명적 — 가스 오르면 공·방부터."+usyn,upsec);
      else if(mxlv<=1) T("tip","up",ut,"공·방 3업이 한타를 가른다 — 병력 뽑으며 꾸준히."+usyn,upsec);
      else if(mxlv>=3) T("good","up",ut,"3업 완성 — 업글 차이가 곧 한타 차이야.",upsec);
      else             T("good","up",ut,"꾸준했어 — 3업까지 마저 채우자.",upsec);
    }else if(up_n===0){
      T("warn","up","업그레이드 없음","물량전은 풀업 싸움 — 가스 오르면 업글부터.");
    }
  }else if(haslv&&mxlv>=1){
    T("good","up","업그레이드 공"+A+"·방"+R+" — 초반부터 투자","짧은 게임인데도 업글을 굴렸네 — 게임이 길어졌으면 그대로 이득이었어.",upsec);
  }

  // 3. 종족별 결정타 (문서 금지사항 기반)
  if(race==="Z"){
    if(mins>=8&&!units["Lurker"]&&!units["Defiler"]) T("tip","comp","러커가 없음","럴커 라인이 있어야 수세에서 벗어나 — 히드라 다음은 럴커.");
    var hiveTech=units["Defiler"]||units["Ultralisk"]||units["Guardian"];
    if(mins>=12&&!hiveTech) T("warn","comp","후반인데 하이브 카드가 없음","온리 히드라는 200 한타에서 녹아 — 하이브 올려 디파일러부터.");
    else if(mins>=9&&mins<12&&!hiveTech) T("tip","comp","하이브 전환 준비할 때","12분 전후 하이브 — 디파일러·가디언이 후반을 가른다.");
  }else if(race==="T"){
    var hasTank=units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"];
    if(mins>=8&&!hasTank) T("warn","comp","탱크 없이 바이오닉만","바이오닉만으론 라인을 못 뚫어 — 팩토리 2개+시즈탱크.");
    if(mins>=9&&!units["Science Vessel"]) T("tip","comp","베슬이 없음","베슬 2~3기가 스웜·클로킹·드랍 대응의 핵심이야.");
    if(marine>=12&&medic===0&&mins>=5) T("warn","comp","메딕 없이 마린만","마린 한 부대당 메딕 3~4기 — 없으면 럴커·스톰에 그냥 녹아.");
    else if(marine>=12&&enemyP>=2&&fbat===0) T("tip","comp","파벳이 없음 (상대 토스 "+enemyP+"명)","발업 질럿엔 파벳이 특효 — 부대에 3기만 섞자.");
  }else if(race==="P"){
    if(mins>=6&&!units["High Templar"]&&!units["Archon"]) T(mins>=8?"warn":"tip","comp","하템(스톰)이 없음","질드라만으론 덩어리를 못 지워 — 스톰 한 방이 한타를 뒤집어.");
    if(mins>=5&&units["Zealot"]&&!units["Dragoon"]) T("tip","comp","드라군 없이 질럿만","질럿만은 대공·사거리가 비어 — 드라군을 섞자.");
    if(p.drops!=null&&(p.drops||0)<1&&!(p.atk_first&&_s2(p.atk_first)<=360)&&mins>=8) T("tip","harass","견제가 적었음","토스의 힘은 견제 — 10분 전엔 한타보다 견제로 이득.");
  }
  if(have_wt.length) T("good","tech","결정타 확보: "+have_wt.join(", "),"후반은 게임체인저 유무로 갈려 — 좋은 판단.");

  // 4. 감지
  if(mins>=6&&race==="P"&&!units["Observer"]&&!bnames.has("Photon Cannon")){
    T("warn","det","감지 수단 없음","다크·러커·마인을 못 보면 그냥 녹아 — 옵저버 1~2기 필수.");
  }else if(mins>=6&&race==="T"&&!units["Science Vessel"]&&!bnames.has("Missile Turret")){
    T("tip","det","감지 수단 부족","다크·클로킹·드랍 대비 터렛/베슬을 챙기자.");
  }

  // 5-0. 초반전(<6분) 전용 — 짧은 게임은 빌드·정찰·첫 교전 타이밍 싸움
  if(ph===0){
    if(p.atk_first&&_s2(p.atk_first)<=270) T("good","rush","이른 선공 "+p.atk_first,"초반전의 주도권은 먼저 때린 쪽 — 타이밍 감각이 좋았어.",_s2(p.atk_first));
    var _oppA=(peers||[]).filter(function(pe){return pe&&pe.team!=null&&p.team!=null&&pe.team!==p.team;}).reduce(function(m,o){return Math.max(m,o.army||0);},0);
    if(mins>=3&&_oppA>=Math.max(8,pyRound(army)*1.6)) T("tip","rush","초반 병력이 상대보다 얇았음","내 ~"+pyRound(army)+" vs 상대 ~"+_oppA+" 서플라이 — 초반전은 첫 교전 병력이 전부야. 일꾼·테크에 너무 투자하면 이 타이밍이 밀려.");
    if(!fast&&workers>=Math.round(mins*9)+6) T("tip","rush","초반전치고 일꾼 투자가 많음","일꾼 "+workers+"기 — 그 자원이면 병력 몇 기가 더 나왔어. 상대 성향을 정찰로 확인한 뒤에 배를 째자.");
  }

  // 5. 멀티 (빨무에선 자원 무한이라 멀티 조언이 무의미 → 건너뜀)
  if(!fast&&race!=="Z"){
    if(tc>=2) T("good","exp","멀티 "+tc+"개 확보","생산처 분산 — 견제 복구도 물량도 빨라져.",(p.townhalls&&p.townhalls[1])?_s2(p.townhalls[1].t):null);
    else if(mins>=6) T("tip","exp","본진 하나 — 멀티 권장","본진 하나는 드랍 한 번에 휘청 — 멀티로 분산하자.");
  }

  // 6. 첫 200 / 물량
  if(maxSup>=190){
    if(have_wt.length) T("good","army","최대 ~"+Math.round(maxSup)+" 풀 병력","조합까지 갖춘 200 — 풀업 되면 바로 진출.");
    else T("tip","army","최대 ~"+Math.round(maxSup)+" — 조합은 아쉬움","빠른 200보다 조합된 200 — 결정타 유닛으로 전환하자.");
  }else if(mins>=9&&maxSup<130){
    T("tip","army","최대 ~"+Math.round(maxSup)+" — 물량 부족","물량이 얇아 — 생산기지를 늘려 자원을 병력으로.");
  }

  // 7. 일꾼 (빨무에선 일꾼 수 조언이 무의미 → 건너뜀; 빨무 전용 팁에서 따로)
  if(!fast){
  if(workers>=40) T("good","worker","일꾼 "+workers+"기 — 경제 탄탄","일꾼=돈=병력 — 경제 기반이 탄탄해.");
  else if(workers<22&&mins>=5) T("tip","worker","일꾼 "+workers+"기 — 부족","~50기까지 꾸준히 — 잘려도 바로 충원.");
  }

  // 8. APM
  if(series.length>=3){
    var body=series.length>3?series.slice(0,-1):series;
    var sorted=body.slice().sort(function(a,b){return a-b;});
    var med=body.length?sorted[Math.floor(body.length/2)]:0;
    var dip=[];body.forEach(function(v,i){if(med>0&&v<med*0.55)dip.push(i);});
    if(dip.length) T("tip","apm",dip[0]+"분에 손이 멈춤","평소("+med+") 절반 이하 — 교전 중에도 생산 단축키로 계속 찍자.",dip[0]*60);
  }
  if(apm&&eapm&&apm-eapm>=70){
    T("tip","apm","APM "+apm+" / 유효 "+eapm,"반복클릭이 많아 — 그 손을 생산·분배에 쓰자.");
  }

  // 9. 정찰 (빨무에선 정찰 타이밍이 무의미 → 건너뜀)
  if(!fast&&p.scouted!=null){
    if(p.scouted===0||!p.scout_first){
      T(ph===0?"warn":"tip","scout","정찰을 거의 안 함",ph===0?"초반전일수록 정찰이 생명 — 상대 올인·생략 빌드를 못 보면 그대로 끝나.":"정찰이 없으면 다크·올인을 모르고 당해 — 초반 한 번은 보자.");
    }else if(_s2(p.scout_first)<150){
      T("good","scout","초반 정찰 "+p.scout_first+(p.scouted>1?" ("+p.scouted+"곳)":""),"일찍 봤네 — 본 정보로 다음 수를 예측하자.",_s2(p.scout_first));
    }else if(_s2(p.scout_first)>240){
      var _std=race==="Z"?"오버로드 2기 직후":"첫 파일런/서플 직후";
      T("tip","scout","정찰이 늦음 "+p.scout_first,"표준은 "+_std+" — 늦으면 대응할 시간이 사라져.",_s2(p.scout_first));
    }
  }
  // 10. 컨트롤 그룹
  if(p.groups!=null&&p.groups<=2){
    T("tip","ctrl","컨트롤 그룹 "+p.groups+"개","그룹을 안 쓰면 교전 중 생산이 끊겨 — 병력/생산 분리 지정.");
  }else if(p.groups!=null&&p.groups>=6){
    T("good","ctrl","컨트롤 그룹 "+p.groups+"개","주력·생산·마법 분리 운용 — 상급 조작.");
  }
  // 11. 드랍 견제
  if(p.drops&&p.drops>=3){
    T("good","drop","드랍 견제 "+p.drops+"회","드랍으로 흔들었네 — 정면 압박과 병행하면 더 강해.");
  }
  // 12. 생산 연속성 (가동률/자원 소비율)
  if(p.prod_max_gap&&p.prod_max_gap>=90){
    T("tip","cont","생산 공백 최대 "+p.prod_max_gap+"초","생산이 끊긴 구간 = 돈 쌓임 신호 — 교전 중에도 계속 찍자.");
  }else if(p.prod_max_gap!=null&&p.prod_max_gap<=35&&(p.total_supply||0)>80){
    T("good","cont","생산 거의 안 끊김","공백 최대 "+p.prod_max_gap+"초 — 교전 중에도 계속 뽑은 최상급.");
  }

  // 13. 상대 비교 — 1v1은 정밀 비교, 팀전(2v2·3v3)은 상대팀 기준으로 발동
  var oppList=(peers||[]).filter(function(pe){return pe&&pe.team!=null&&p.team!=null&&pe.team!==p.team;});
  var oAny=function(n){return oppList.some(function(o){return o.uset&&o.uset.has(n);});};
  var vsT=oppList.some(function(o){return o.race==="T";}),vsP=oppList.some(function(o){return o.race==="P";}),vsZ=oppList.some(function(o){return o.race==="Z";});
  var obs=(units["Observer"]||{}).n||0;
  var legZ=bnames.has("Leg Enhancements");
  var hasVes=!!units["Science Vessel"];
  var hasTankU=!!(units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"]);
  var late=(mins>=14)||(maxSup>=160);
  if(oppList.length){
    var is1=oppList.length===1;
    var best=oppList.reduce(function(a,b){return (((b.atk_lv||0)+(b.arm_lv||0))>((a.atk_lv||0)+(a.arm_lv||0)))?b:a;},oppList[0]);
    var who=is1?"상대":"상대팀 최고";
    var dup=((best.atk_lv||0)+(best.arm_lv||0))-(A+R);
    if(dup>=2) T("warn","vs","업그레이드가 "+who+"보다 낮음","공"+A+"방"+R+" vs 공"+(best.atk_lv||0)+"방"+(best.arm_lv||0)+" — 두 단계 차이는 한타가 그냥 갈려.",upsec);
    else if(dup===1) T("tip","vs","업글이 "+who+"보다 한 단계 낮음","공"+A+"방"+R+" vs 공"+(best.atk_lv||0)+"방"+(best.arm_lv||0)+". 한 단계만 따라붙어도 교전 결과가 달라져.",upsec);
    if(is1){
      var opp=oppList[0];
      if(!fast){var dw=(opp.workers||0)-workers;
      if(dw>=15) T("warn","vs","일꾼이 상대보다 "+dw+"기 적음","상대 "+opp.workers+" vs 나 "+workers+" — 경제가 밀리면 물량·업글이 통째로 밀려.");
      else if(dw>=8) T("tip","vs","일꾼이 상대보다 "+dw+"기 적음","상대("+opp.workers+") 대비 경제가 조금 뒤졌어("+workers+"). 견제받는 중이 아니면 일꾼을 꾸준히 더 돌리자.");}
      if(!fast){var myNat=(p.townhalls&&p.townhalls.length>=2)?p.townhalls[1].t:null;
      if(myNat&&opp.nat){var de=_s2(myNat)-_s2(opp.nat);
        if(de>=90) T("tip","vs","앞마당이 상대보다 "+de+"초 늦음","앞마당 "+myNat+" vs "+opp.nat+" — 확장이 늦으면 경제가 통째로 밀려.",_s2(myNat));}
      if((opp.tcount||0)-tc>=2) T("tip","vs","기지 수가 상대보다 적음","기지 "+tc+" vs "+opp.tcount+" — 안전할 때 미리 가져가자.");}
    }

    // 14. 매치업 코칭 — 상대팀에 해당 종족·유닛이 있으면 발동 (팀전 포함)
    if(race==="T"&&(oAny("Carrier")||oAny("Arbiter"))&&!units["Goliath"]) T("warn","mu","상대 캐리어/아비터인데 골리앗이 없음","골리앗+사거리업으로 공중을 받쳐야 해.");
    if(race==="Z"&&oAny("Corsair")&&!units["Scourge"]) T("tip","mu","상대 커세어엔 스컬지","스컬지로 커세어를 줄여 오버로드를 지키자.");
    if(!fast){
      var myGate=build.filter(function(b){return b.name==="Gateway";}).length;
      if(race==="P"&&vsT){
        if(is1&&myGate>0&&oppList[0].fact>0&&myGate<oppList[0].fact+2) T("warn","mu","게이트웨이가 팩토리보다 적음","게이트 "+myGate+" vs 팩 "+oppList[0].fact+" — 기준은 팩토리+2.");
        if(obs<2&&mins>=8) T("tip","mu","옵저버가 부족 (PvT)","옵저버 2~3기로 마인 제거 — 드라군이 안 녹아.");
        if(units["Zealot"]&&!legZ&&mins>=8) T("tip","mu","질럿 발업(Leg)이 없음","발업 질럿이 마인을 밟고 탱크 볼리를 받아줘 — 시타델부터.");
        if(late&&!units["Arbiter"]&&!units["Carrier"]) T("warn","mu","후반 아비터/캐리어가 없음 (PvT)","시즈 라인은 아비터(스테이시스·리콜)로 푼다.");
      }
      if(race==="T"&&vsP&&!units["Vulture"]&&mins>=6) T("tip","mu","벌처가 안 보임 (TvP)","벌처+마인이 질럿을 막고 드라군을 묶어.");
      if(race==="P"&&vsZ){
        if(!units["Corsair"]&&!bnames.has("Photon Cannon")&&mins>=6) T("warn","mu","커세어가 없음 (PvZ)","커세어가 정찰·제공권의 전부 — 스타게이트부터.");
        if(units["Zealot"]&&!legZ&&mins>=8) T("tip","mu","발업 질럿으로 맵 컨트롤 (PvZ)","커세어+발업 질럿으로 저그를 수세로 묶자.");
      }
      if(race==="T"&&vsZ&&hasVes&&hasTankU&&mxlv<1) T("tip","mu","베슬+탱크 타이밍엔 공1방1을 붙여라","첫 진출엔 공1방1 — 노업 진출은 손해만 봐.");
      if(race==="Z"&&vsT&&!units["Lurker"]&&mins>=8) T("tip","mu","럴커 컨테인으로 지연 (ZvT)","럴커로 진출로를 막아 하이브까지 시간을 벌자.");
      if(race==="P"&&vsP){
        if(obs<1&&mins>=6) T("warn","mu","옵저버 없이 PvP (다크/리버 위험)","다크·리버 드랍을 못 보면 무너져 — 옵저버 필수.");
        if(!units["Reaver"]&&mins>=7) T("tip","mu","리버는 PvP의 핵심","셔틀 리버로 프로브를 지지면 경제가 벌어져.");
      }
      if(race==="T"&&vsT&&!hasTankU&&mins>=7) T("tip","mu","시즈 라인이 TvT의 전부","시즈 포지션이 전부 — 드랍십으로 교착을 깨자.");
      if(race==="Z"&&vsZ&&!units["Mutalisk"]&&mins>=5) T("warn","mu","ZvZ는 뮤탈+스컬지 싸움","뮤탈+스컬지 제공권이 승패 — 스파이어부터.");
    }
  }

  // 15. 빠른무한(빨무) 전용 — 매판 같은 문구를 반복하지 않고, 조건이 걸릴 때만
  if(fast){
    if(ph>0&&(prodN<tgt||mxlv<2)) T("tip","fast","빨무 핵심: 물량·업글·조합","남는 돈은 "+prodKo+"·업글·결정타로 — 조합된 물량이 전부야.");
    // 일꾼 50 목표 — 빨무도 초반 일꾼 러시가 기본: 50기까지 쉼 없이, 그 뒤 전부 병력
    var w50=(p.worker50_sec!=null)?p.worker50_sec:null;
    if(w50!=null&&w50<=210) T("good","fast","일꾼 50기 "+_mmss(w50)+" 도달","빨무 정석 페이스 — 이 경제가 물량의 심장.");
    else if(w50!=null&&w50<=330) T("tip","fast","일꾼 50기 "+_mmss(w50)+" — 조금 늦음","첫 2~3분은 일꾼에 올인해서 3분대 안에 50을 채우자.");
    else if(w50!=null) T("tip","fast","일꾼 50기가 "+_mmss(w50)+"에야","너무 늦어 — 초반 일꾼 러시로 50기를 먼저, 병력은 그다음.");
    else if(mins>=6&&workers<50) T("tip","fast","일꾼 "+workers+"기 — 50까지 채우자","빨무도 경제가 우선: 50기까지 쉼 없이 뽑고, 이후 전부 병력으로.");
    if(race==="P"&&mins>=8){
      if(!units["Shuttle"]&&!units["Reaver"]) T("tip","fast","셔틀 견제가 없음 (빨무)","셔틀 리버가 승리 공식 — 로보틱스부터.");
      else if(p.drops&&p.drops>=2) T("good","fast","셔틀 견제 운용 (빨무)","빨무 토스의 승리 공식 — 정면과 병행하면 더 강해.");
    }
    if(race==="T"&&mins>=8&&!(hasTankU&&units["Goliath"])) T("tip","fast","탱크+골리앗 축이 아직 (빨무)","넓게 펼친 탱크+골리앗으로 센터를 가르자.");
    if(race==="Z"&&oAny("Valkyrie")&&!units["Devourer"]) T("warn","fast","상대 발키리엔 디바우러 (빨무)","디바우러로 발키리를 걷어내야 화력이 살아.");
  }

  // 16. 물량 곡선 — 인구/일꾼 시계열 기반 (supply_series · worker50_sec · wipe 리필)
  var SS=p.supply_series,STP=p.supply_step||15;
  var t200s=p.supply200?_s2(p.supply200):null;
  if(fast){
    if(t200s!=null&&t200s<=420) T("good","fast","첫 200 "+p.supply200,"물량 엔진이 살아있어 — 한타 후에도 이 리필 속도가 승부를 가른다.");
    else if(t200s!=null&&t200s>540) T("tip","fast","첫 200이 "+p.supply200+" — 늦음","생산 라인·라바 회전을 늘려 200 도달을 앞당기자. 빨무 승부는 200 리필 싸움.");
    else if(t200s==null&&mins>=9) T("tip","fast","200을 못 채움 (최대 "+maxSup+")","자원은 무한 — 인구가 안 차는 건 생산 라인 문제. "+prodKo+"부터 점검.");
  }
  if(SS&&SS.length>8){
    var _g0=-1,_gl=0,_best=null,_k;
    for(_k=Math.max(1,Math.floor(120/STP));_k<SS.length;_k++){
      if(SS[_k]-SS[_k-1]<0.5){if(_g0<0)_g0=_k-1;_gl=_k-_g0;}
      else{if(_g0>=0&&_gl*STP>=60&&(!_best||_gl>_best.l))_best={s:_g0*STP,l:_gl};_g0=-1;_gl=0;}
    }
    if(_g0>=0&&_gl*STP>=60&&(!_best||_gl>_best.l))_best={s:_g0*STP,l:_gl};
    if(_best&&_best.s<mins*60-45)
      T("tip","prod","생산 공백 "+_mmss(_best.s)+"~"+_mmss(_best.s+_best.l*STP),
        (fast?"빨무에선 치명적 — ":"")+Math.round(_best.l*STP)+"초 동안 생산이 멈췄어. 교전 중에도 생산 사이클은 계속 돌려야 물량이 유지돼.",_best.s);
    (p._wipes||[]).slice(0,2).forEach(function(_ws){
      var k0=Math.min(SS.length-1,Math.floor(_ws/STP)),k1=Math.min(SS.length-1,Math.floor((_ws+60)/STP));
      if(k1<=k0)return;var _d=Math.max(0,SS[k1]-SS[k0]);
      if(_d>=40) T("good","wipe","몰살 후 리필 +"+Math.round(_d)+" ("+_mmss(_ws)+")","병력을 크게 잃고 1분 만에 +"+Math.round(_d)+" 인구 재생산 — 빨무의 정답 그 자체.",_ws);
      else T("tip","wipe",_mmss(_ws)+" 대량 손실 후 리필 저조","이후 1분 생산이 +"+Math.round(_d)+" 인구뿐 — 잃는 그 순간이 생산 최대 가동 타이밍이야.",_ws);
    });
  }

  // 17. HUD 실측 (녹화자 전용) — 재-200 시간·200 회복 실패·자원 유휴는 화면에서 읽은 진짜 값
  if(p._hud){
    var HD=p._hud,st5=HD.step||5;
    (HD.re200||[]).slice(0,2).forEach(function(rr){var dt=rr.t-rr.w;
      if(dt<=50) T("good","wipe","재-200 "+_mmss(rr.t)+" — 몰살 후 "+dt+"초 (실측)","잃자마자 도로 꽉 채웠어. 이 리필 속도가 빨무의 체급이야.",rr.t);
      else T("tip","wipe","재-200까지 "+dt+"초 ("+_mmss(rr.w)+"→"+_mmss(rr.t)+", 실측)","몰살 후 인구 복구가 느려 — 생산 라인 추가·예약 생산을 습관화하자.",rr.w);});
    (HD.wipes||[]).forEach(function(wv){
      if(!(HD.re200||[]).some(function(r){return r.w===wv;})&&(mins*60-wv)>60)
        T("tip","wipe",_mmss(wv)+" 몰살 후 200 회복 실패 (실측)","경기 끝까지 인구를 못 되채웠어. 남는 자원부터 확인하고 생산에 전부 환원.",wv);});
    if(HD.mn&&HD.mn.length>12){var hoard=0,hs=0,q;
      for(q=12;q<HD.mn.length;q++){var m60=Math.min.apply(null,HD.mn.slice(q-12,q+1));
        if(m60>hoard){hoard=m60;hs=Math.max(0,q*st5-(HD.lead||0));}}
      var lim=fast?1500:800;
      if(hoard>=lim) T("tip","fast","미네랄 "+hoard+" 유휴 — "+_mmss(hs)+" 부근 (실측)","1분 내내 이만큼이 안 쓰였어. "+(fast?"빨무에서 노는 미네랄 = 안 나온 병력.":"생산·확장에 즉시 환원하자."),hs);
      else if(fast&&mins>=8) T("good","fast","자원 회전 우수 (실측)","미네랄 유휴가 "+lim+" 미만 — 캐는 족족 병력으로. 물량의 비결.");}
  }

  // 18. 종료 점수판 (실측) — 총점/자원 점수 상대 비교
  if(p._es&&p._esAll){
    var _nm2=Object.keys(p._esAll);
    if(_nm2.length>=2){
      var _tops=_nm2.reduce(function(m2,k2){return Math.max(m2,p._esAll[k2].t||0);},0);
      var _topr=_nm2.reduce(function(m2,k2){return Math.max(m2,p._esAll[k2].r||0);},0);
      if((p._es.t||0)===_tops&&_tops>0) T("good","score","점수판 총점 1위 ("+p._es.t+")","종료 점수판 실측 — 생산·파괴·채취 모두에서 판을 지배했어.");
      if(_topr>0&&(p._es.r||0)<_topr*0.6) T("tip","score","자원 채취 열세 (점수판 "+p._es.r+" vs 최고 "+_topr+")","일꾼 가동이 밀렸단 뜻 — 일꾼 충원과 분산 채취부터.");
    }
  }

  // 총평 (강점 + 1순위 개선 + 격려)
  var strong=[];
  if(prodN>=tgt) strong.push("생산기지");
  if(mxlv>=3) strong.push("풀업(공"+A+"방"+R+")"); else if(mxlv>=2) strong.push("업글");
  if(have_wt.length) strong.push("결정타 유닛");
  if(workers>=40) strong.push("경제");
  if(maxSup>=190&&have_wt.length) strong.push("조합된 물량");
  if(p.drops&&p.drops>=3) strong.push("견제");
  var hasTank2=units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"];
  var fixes=[];
  if(mins>=7&&mxlv===0&&(haslv||up_n===0)) fixes.push("공·방 업그레이드");
  if(mins>=7&&race==="P"&&!units["High Templar"]&&!units["Archon"]) fixes.push("하이템플러 스톰");
  if(race==="Z"&&mins>=12&&!hiveTech) fixes.push("하이브 전환(디파일러)");
  if(race==="T"&&mins>=8&&!hasTank2) fixes.push("시즈탱크");
  if(race==="T"&&marine>=12&&medic===0) fixes.push("메딕 추가");
  if(prodN<Math.max(2,tgt*0.6)) fixes.push(prodKo+" 수 늘리기");
  if(mins>=8&&race==="Z"&&!units["Lurker"]&&!units["Defiler"]) fixes.push("럴커");
  if(maxSup>=190&&!have_wt.length&&!fixes.length) fixes.push("결정타 유닛 전환");
  if(mxlv>0&&mxlv<3&&!fixes.length) fixes.push("3업까지");
  if(ph===0&&!fast&&(p.scouted===0||!p.scout_first)) fixes.unshift("초반 정찰");
  var sstr=strong.length?strong.slice(0,3).join("·"):null;
  var verdict;
  if(!fixes.length) verdict=sstr?("이번 판은 군더더기 없이 탄탄해 — "+sstr+"까지 다 챙겼어. 이대로면 한타도 후반도 강해."):"무난하게 잘 풀어낸 한 판이야.";
  else if(fixes.length===1) verdict=(sstr?(sstr+"까진 잘 갖췄어. "):"")+"딱 하나, "+fixes[0]+"만 더 챙기면 한 단계 올라가.";
  else verdict=(sstr?("강점은 "+sstr+". "):"")+"개선 1순위는 "+fixes[0]+", 그다음 "+fixes[1]+" — 이 둘만 잡으면 확 달라져.";
  if(ph===0) verdict="~"+Math.round(mins)+"분 초반전이라 긴 게임 지표(업글·조합·멀티)는 평가에서 뺐어. "+verdict;

  // 5축 등급 (S/A/B/C) — 리포트 상단 요약용
  var coreOK=race==="T"?!!hasTank2:(race==="P"?!!(units["High Templar"]||units["Archon"]):!!(units["Lurker"]||hiveTech));
  var g_cont=(p.prod_max_gap==null)?null:(p.prod_max_gap<=35?"S":p.prod_max_gap<=60?"A":p.prod_max_gap<=90?"B":"C");
  var g_har=(p.drops==null&&!p.atk_first)?null:((p.drops||0)>=3?"S":(p.drops||0)>=1?"A":(p.atk_first&&_s2(p.atk_first)<=420?"B":"C"));
  var grades=[
    {k:"생산",g:prodN>=tgt+2?"S":prodN>=tgt?"A":prodN>=Math.max(2,tgt*0.6)?"B":"C"},
    {k:"업글",g:ph===0?null:((!haslv&&up_n===0)?"C":(mxlv>=3?"S":mxlv===2?"A":mxlv===1?"B":"C"))},
    {k:"조합",g:ph===0?null:(have_wt.length>=2?"S":(have_wt.length?"A":(coreOK?"B":"C")))},
    {k:"가동률",g:g_cont},
    {k:"견제",g:g_har}
  ].filter(function(x){return x.g;});

  return [timings,pts,verdict,grades];
}

/* ═══ 코치 2.0 — 인과 체인: '이 판의 핵심' 스토리 (빨무 벤치마크 기반) ═══ */
var BM_FAST={lurker:504,lurker_late:564,vsacs_gap:120,drop_first:634,defiler:871,
             siege:330,vessel:599,storm:515,obs_gap:60};   // 이 갤러리 승자 실측과 동기화
function _uT(p,k){var u=(p.units||[]).find?((p.units||[]).find(function(x){return x&&x.name===k;})):null;
  return (u&&u.first)?_s2(u.first):null;}
function _tT(p,k){var m=p.tech1||{};return (k in m)?_s2(m[k]):null;}
function chain_stories(a,p,peers,fast,won){
  if(!p||(!p.tech1&&!(p.units&&p.units[0]&&('first' in p.units[0]))))return [];   // 구버전 데이터 가드
  var S=[],mins=_s2((a.meta&&a.meta.length)||'0:0')/60;
  var opp=(peers||[]).filter(function(q){return q.team!==p.team;});
  var oppLurk=1e9;opp.forEach(function(q){var t=_uT(q,'Lurker');if(t!=null&&t<oppLurk)oppLurk=t;});
  function story(id,sc,title,ev,rx){S.push({id:id,score:sc,t:title,ev:ev||[],rx:rx});}
  var rl=p.rl||({zerg:'Z',ran:'T',toss:'P'})[p.race]||'';
  if(rl==='Z'&&mins>=7){
    var lk=_uT(p,'Lurker'),la=_tT(p,'Lurker Aspect'),
        vs=_tT(p,'Ventral Sacs (Overlord Transport)'),dr=(p.drop_secs&&p.drop_secs[0])||null;
    if(lk==null&&la==null)
      story('no-lurker',won?55:82,'럴커 라인 부재',[],
        '다음 판: 해처리 2개째 타이밍에 럴커덴 → 레어 직후 아스펙트. 빨무 저그의 허리는 럴커야.');
    else if(lk!=null&&lk>BM_FAST.lurker_late)
      story('late-lurker',(won?50:85)+Math.min(15,Math.round((lk-BM_FAST.lurker)/30)),
        '럴커가 늦었다 — '+_mmss(lk),[['럴커 첫 등장',lk,'기준 ~'+_mmss(BM_FAST.lurker)]],
        '스포닝 직후 가스 → 레어 → 아스펙트를 한 호흡으로. 목표 '+_mmss(BM_FAST.lurker)+' — 럴커가 늦으면 뒤 라인 전부가 밀린다.');
    if((lk!=null||la!=null)&&(vs==null||(lk!=null&&vs>lk+BM_FAST.vsacs_gap))){
      var ev=[];if(lk!=null)ev.push(['럴커',lk,null]);if(vs!=null)ev.push(['수송업 시작',vs,'럴커 +'+Math.round(vs-lk)+'초']);
      story('late-vsacs',won?45:76,(vs==null?'오버 수송업 미확보 — 드랍 불가':'수송업이 늦어 드랍 지연'),ev,
        '레어 완성 즉시 수송업. 럴커 드랍이 견제의 본체 — 수송업 없는 럴커는 반쪽이야.');}
    if((vs!=null)&&(dr==null||dr>BM_FAST.drop_first+120))
      story('late-drop',won?40:70,(dr==null?'수송업은 됐는데 드랍 0회':'첫 드랍 '+_mmss(dr)+' — 늦음'),
        (dr!=null?[['첫 드랍',dr,'기준 ~'+_mmss(BM_FAST.drop_first)]]:[['수송업',vs,null]]),
        '수송업 완성 30초 안에 첫 드랍. 럴커 2기+저글링이면 충분 — 타이밍이 화력보다 중요해.');
    if(mins>=11.5&&_uT(p,'Defiler')==null)
      story('no-defiler',won?28:55,'디파일러 부재(후반)',[],'11~12분엔 디파일러 — 다크스웜 없인 후반 한타를 못 이겨.');
  }
  if(rl==='T'){
    var sg=_tT(p,'Tank Siege Mode');
    if(mins>=6&&sg==null)story('no-siege',won?32:62,'시즈모드 미개발',[],'팩토리 애드온에서 시즈부터 — 탱크는 시즈가 본체.');
    else if(sg!=null&&sg>BM_FAST.siege+90)story('late-siege',won?30:58,'시즈가 늦었다 — '+_mmss(sg),[['시즈모드',sg,'기준 ~'+_mmss(BM_FAST.siege)]],'첫 팩토리에 바로 애드온 — 시즈 타이밍이 수비선 타이밍이야.');
    if(oppLurk<1e9&&mins>=9&&_uT(p,'Science Vessel')==null)
      story('no-vessel',won?35:72,'상대 럴커('+_mmss(oppLurk)+')인데 베슬 부재',[['상대 럴커',oppLurk,null]],
        '스타포트→사이언스 퍼실리티. 베슬 없인 럴커 라인을 못 넘는다.');
  }
  if(rl==='P'){
    if(oppLurk<1e9){var ob=_uT(p,'Observer');
      if(ob==null||ob>oppLurk+BM_FAST.obs_gap)
        story('late-obs',won?40:78,(ob==null?'옵저버 부재 — 상대 럴커에 무방비':'옵저버('+_mmss(ob)+')가 럴커보다 늦음'),
          [['상대 럴커',oppLurk,null]].concat(ob!=null?[['옵저버',ob,null]]:[]),
          '상대 저그면 로보틱스는 보험이 아니라 필수 — 옵저버가 럴커보다 먼저여야 해.');}
    var st=_tT(p,'Psionic Storm');
    if(mins>=8&&st==null)story('no-storm',won?28:58,'스톰 부재',[],'템플러 아카이브 → 스톰. 빨무 물량전의 정답 카드.');
  }
  S.sort(function(x,y){return y.score-x.score;});
  return S.slice(0,2);
}

/* ═══ 코치 3.0 — 전략 인식 → 실행 채점 → 칭찬/시각 처방 ═══
   CAL = 이 갤러리 63판 '승자 중앙값' 실측(초). 재보정 SQL: journal 참조. */
var META={corsair:80,arbiter:78,htemp:71,shuttle:71,obs:65,vessel:64,dark:62,reaver:58,vulture:21,lurker:42};  // 유닛 보유 시 승률% (이 방 실측)
var CAL={w50:{t:360,s:45},s200:{t:564,s:60},corsair:{t:420,s:90},lurker:{t:504,s:60},defiler:{t:871,s:100},mutal:{t:751,s:120},
 shuttle:{t:405,s:60},reaver:{t:469,s:75},htemp:{t:470,s:75},dark:{t:445,s:75},
 obs:{t:619,s:90},vulture:{t:206,s:60},vessel:{t:599,s:90},dropship:{t:546,s:80},
 siege:{t:330,s:90},stim:{t:260,s:90},vsacs_gap:60,drop_gap:130};
function _uN(p,k){var u=(p.units||[]).find(function(x){return x&&x.name===k;});return u?(u.n||0):0;}
function strategy_report(a,p,peers,fast,won){
 try{
  if(!p||!p.units||!p.units.length||!(p.units[0]&&('first' in p.units[0])))return null;
  var mins=_s2((a.meta&&a.meta.length)||'0:0')/60, hasTech=!!p.tech1;
  var rl=p.rl||({zerg:'Z',ran:'T',toss:'P'})[p.race]||'';
  var opp=(peers||[]).filter(function(q){return q.team!==p.team;});
  var oppCloak=opp.some(function(q){return _uN(q,'Lurker')>0||_uN(q,'Dark Templar')>0;});
  // ── 1) 전략 인식 ──
  var A=[];
  function arch(id,label,score,cps){if(score>0)A.push({id:id,label:label,score:score,cps:cps});}
  if(rl==='Z'){
    arch('z-lurker','럴커 운영', (_uN(p,'Lurker')>=2?3:0)+(_tT(p,'Lurker Aspect')!=null?2:0),[
      {lb:'럴커',u:'Lurker',cal:CAL.lurker,fix:'해처리 2개째에 럴커덴 → 레어 완성 즉시 아스펙트'},
      {lb:'수송업',tech:'Ventral Sacs (Overlord Transport)',cal:{t:CAL.lurker.t+CAL.vsacs_gap,s:60},fix:'레어 뜨면 오버 수송업부터'},
      {lb:'첫 드랍',drop:1,cal:{t:CAL.lurker.t+CAL.drop_gap,s:70},fix:'수송업 완성 30초 안에 럴커 2기 드랍'},
      {lb:'디파일러',u:'Defiler',cal:CAL.defiler,min:13,fix:'13~14분 하이브 → 디파일러로 후반 전환'}]);
    arch('z-muta','뮤탈 전환', _uN(p,'Mutalisk')>=6?3:0,[
      {lb:'뮤탈',u:'Mutalisk',cal:CAL.mutal,fix:'스파이어 타이밍을 앞당겨 첫 뮤탈 웨이브를 세게'}]);
  }
  if(rl==='T'){
    arch('t-mech','벌처·메카닉', (_uN(p,'Vulture')>=4?3:0)+(_tT(p,'Tank Siege Mode')!=null?1:0),[
      {lb:'첫 벌처',u:'Vulture',cal:CAL.vulture,fix:'팩토리 완성 즉시 벌처 — 3:30 전 첫 견제'},
      {lb:'시즈모드',tech:'Tank Siege Mode',cal:CAL.siege,fix:'첫 팩 애드온에서 시즈 연구'},
      {lb:'베슬',u:'Science Vessel',cal:CAL.vessel,when:oppCloak,fix:'상대 은폐 유닛 — 스타포트→베슬 필수'}]);
    arch('t-bio','바이오닉 드랍', (_uN(p,'Marine')>=12?2:0)+(_uN(p,'Dropship')>=1?2:0),[
      {lb:'스팀팩',tech:'Stim Packs',cal:CAL.stim,fix:'아카데미 완성 즉시 스팀'},
      {lb:'드랍십',u:'Dropship',cal:CAL.dropship,fix:'9분 전 첫 드랍십 — 마린메딕 8+2'}]);
  }
  if(rl==='P'){
    arch('p-reaver','리버 드랍', (_uN(p,'Reaver')>=1?2:0)+(_uN(p,'Shuttle')>=1?2:0),[
      {lb:'셔틀',u:'Shuttle',cal:CAL.shuttle,fix:'로보틱스 완성 즉시 셔틀'},
      {lb:'리버',u:'Reaver',cal:CAL.reaver,fix:'서포트베이 선착공 — 이 방 승자들의 1등 카드야'}]);
    arch('p-corsair','커세어 제공권', _uN(p,'Corsair')>=4?3:0,[
      {lb:'커세어',u:'Corsair',cal:CAL.corsair,fix:'스타게이트 2개 — 커세어 6기+로 오버로드·셔틀부터 끊어'}]);
    arch('p-storm','스톰 운영', (_uN(p,'High Templar')>=2?2:0)+(_tT(p,'Psionic Storm')!=null?2:0),[
      {lb:'하이템플러',u:'High Templar',cal:CAL.htemp,fix:'시타델→아카이브를 끊지 말고'},
      {lb:'스톰',tech:'Psionic Storm',cal:{t:CAL.htemp.t+45,s:70},fix:'아카이브 완성 즉시 스톰 연구'},
      {lb:'옵저버',u:'Observer',cal:CAL.obs,when:oppCloak,fix:'상대 은폐 — 옵저버는 필수'}]);
    arch('p-dark','다크 견제', _uN(p,'Dark Templar')>=2?2:0,[
      {lb:'다크',u:'Dark Templar',cal:CAL.dark,fix:'질럿 페이크 후 다크 3기 타이밍'}]);
  }
  if(!A.length)return null;
  A.sort(function(x,y){return y.score-x.score;});
  var top=A[0]; if(top.score<2)return null;
  // ── 2) 실행 채점 (기초체력 공통 + 아키타입 체크포인트) ──
  var cps=[];
  if(p.worker50_sec!=null)cps.push({lb:'일꾼 50',raw:p.worker50_sec,cal:CAL.w50,fix:'6:00 전 일꾼 50 — 물량의 연료'});
  if(mins>=9.5)cps.push({lb:'첫 200',raw:(p.supply200!=null?_s2(p.supply200):null),cal:CAL.s200,fix:'9:24 전 200 — 이 방 최대 승리 변수(도달 시 승률 56%, 미도달 36%)'});
  cps=cps.concat(top.cps);
  var items=[],hit=0,tot=0;
  cps.forEach(function(cp){
    if(cp.when===false)return;
    if(cp.min&&mins<cp.min)return;
    var act=null;
    if('raw' in cp)act=cp.raw;
    else if(cp.u)act=_uT(p,cp.u);
    else if(cp.tech){if(!hasTech)return;act=_tT(p,cp.tech);}   // 구데이터: 판정 제외
    else if(cp.drop)act=(p.drop_secs&&p.drop_secs[0])||null;
    tot++;
    var tgt=cp.cal.t,ok=(act!=null&&act<=tgt+cp.cal.s);
    if(ok)hit++;
    items.push({lb:cp.lb,act:act,tgt:tgt,ok:ok,fix:cp.fix});
  });
  if(!tot)return null;
  var rate=hit/tot;
  // ── 3) 출력: 칭찬 or 시각 박힌 처방 ──
  var line;
  if(rate>=0.75){
    var good=items.filter(function(i){return i.ok;}).map(function(i){return i.lb+' '+_mmss(i.act);}).join(' · ');
    var why={'p-corsair':' (이 방 커세어 보유 승률 80%)','p-reaver':' (이 방 셔틀 보유 승률 71%)','p-storm':' (이 방 하템 보유 승률 71%)'}[top.id]||'';
    line={tone:'good',txt:'전략 실행 우수 — '+good+'. 이 리듬 그대로, 다음 판은 같은 빌드에서 물량만 한 단계 위로.'+why};
  }else{
    var miss=items.filter(function(i){return !i.ok;});
    var steps=miss.map(function(i,ix){
      return (ix+1)+') '+_mmss(i.tgt)+' '+i.lb+(i.act!=null?' (오늘 '+_mmss(i.act)+')':' (오늘 없음)')+' — '+i.fix;
    }).join('  ');
    line={tone:'fix',txt:'다음 판 체크리스트: '+steps};
  }
  if(top.id==='t-mech'&&_uN(p,'Vulture')>=10)
    line.txt+=' ⚠ 이 방 벌처 다량 승률 21% — 벌처는 초반 견제까지만, 중반엔 탱크·베슬 전환.';
  if(top.id==='z-lurker')
    line.txt+=' 참고: 이 방은 커세어·하템 강세 — 럴커 곁에 히드라·스컬지 커버를 붙여.';
  return {label:top.label,rate:rate,items:items,line:line};
 }catch(_e){return null;}
}
function coach_report(a){
  var mins=(function(){var L=(a.meta&&a.meta.length)||"0:0";var q=(""+L).split(":");return ((+q[0])*60+(+q[1]||0))/60;})();
  const base=[];
  (a.players||[]).forEach(p=>{
    const unames=(p.units||[]).map(u=>u.name);
    const race=_coach_race(p.race,unames);const build=p.build||[];
    var units={};(p.units||[]).forEach(u=>units[u.name]=u);
    var workers=0,army=0;Object.keys(units).forEach(n=>{if(COACH_WORKERS.has(n))workers+=units[n].n;else army+=units[n].n*(COACH_SUPPLY[n]||1);});
    var th=p.townhalls||[];
    base.push({prod:build.filter(b=>COACH_PROD[race].has(b.name)).length,race:race,team:p.team,
      name:p.name,workers:workers,army:pyRound(army),atk_lv:p.atk_lv||0,arm_lv:p.arm_lv||0,
      tcount:th.length,nat:(th.length>=2?th[1].t:null),total_supply:p.total_supply||0,
      gate:build.filter(b=>b.name==='Gateway').length, fact:build.filter(b=>b.name==='Factory').length,
      uset:new Set(Object.keys(units).filter(n=>units[n].n>0))});
  });
  var fast=/(빨무|빠무|무한|fastest)/i.test((a.meta&&a.meta.map)||"");
  var _wmap={};((a.highlights)||[]).forEach(function(h){if(h&&h.kind==='wipe'&&h.who){(_wmap[h.who]=_wmap[h.who]||[]).push(h.sec||0);}});
  const out=[];
  (a.players||[]).forEach((p,i)=>{
    const peers=base.filter((b,j)=>j!==i);
    p._wipes=_wmap[p.name]||[];
    p._hud=(a.hud&&a.hud.who===p.name)?a.hud:null;
    p._es=(a.endscore&&a.endscore[p.name])||null;
    p._esAll=a.endscore||null;
    const r=coach_player(p,peers,mins,fast);
    try{r.stories=chain_stories(a,p,(a.players||[]).filter((b,j)=>j!==i),fast,(a.meta&&a.meta.winner)===p.team);}catch(_e){r.stories=[];}
    try{r.strat=strategy_report(a,p,(a.players||[]).filter((b,j)=>j!==i),fast,(a.meta&&a.meta.winner)===p.team);}catch(_e){r.strat=null;}
    out.push({id:p.id,name:p.name,race:p.race,timings:r[0],points:r[1],verdict:(fast?"[빠른무한 모드] ":"")+r[2],grades:r[3]||[],stories:(r.stories||[]),strat:(r.strat||null)});
  });
  return out;
}
