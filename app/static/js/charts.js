'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const source = document.getElementById('chart-data');
  if (!source || typeof Chart === 'undefined') return;
  const data = JSON.parse(source.textContent);
  const teal = '#10a38a', orange = '#e6ac78', blue = '#9fbfda';
  Chart.defaults.font.family = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 10; Chart.defaults.color = '#96a5ae';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 7;
  Chart.defaults.plugins.legend.labels.padding = 18;
  Chart.defaults.plugins.tooltip.backgroundColor = '#153441';
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  const currency = value => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(value);
  const short = value => Math.abs(value) >= 100000 ? (value/100000).toLocaleString('en-IN',{maximumFractionDigits:1})+'L' : Math.abs(value) >= 1000 ? (value/1000).toLocaleString('en-IN',{maximumFractionDigits:1})+'k' : value.toLocaleString('en-IN');
  function cartesian(money=true, legend=false) {
    return {responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false}, plugins:{legend:{display:legend,position:'bottom'},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${money?currency(c.parsed.y):c.parsed.y}`}}},scales:{x:{grid:{display:false},border:{display:false},ticks:{maxRotation:0,maxTicksLimit:6,font:{size:9},padding:8}},y:{beginAtZero:true,border:{display:false},grid:{color:'#f0f3f4'},ticks:{padding:10,maxTicksLimit:5,precision:money?undefined:0,callback:v=>money?'₹'+short(v):v}}}};
  }
  function make(id,type,chartData,options,plugins=[]) { const canvas=document.getElementById(id); if(canvas) new Chart(canvas,{type,data:chartData,options,plugins}); }
  const emptyRing={id:'emptyRing',afterDraw(chart){const sum=chart.data.datasets[0].data.reduce((a,b)=>a+b,0);if(sum)return;const {ctx,chartArea:{left,right,top,bottom}}=chart;const x=(left+right)/2,y=(top+bottom)/2,r=Math.min(right-left,bottom-top)*.32;ctx.save();ctx.strokeStyle='#f0f4f3';ctx.lineWidth=24;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#9aaba7';ctx.font='10px Inter, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('No activity yet',x,y);ctx.restore();}};
  function donutOptions(money=true,legend=false) {return {responsive:true,maintainAspectRatio:false,cutout:'76%',plugins:{legend:{display:legend,position:'bottom'},tooltip:{callbacks:{label:c=>`${c.label}: ${money?currency(c.parsed):c.parsed+' transactions'}`}}}};}
  make('dashboard-trend','line',{labels:data.labels,datasets:[{label:'Closing balance',data:data.balances,borderColor:teal,backgroundColor:'#0ea58c0a',borderWidth:2,fill:true,tension:.35,pointRadius:3,pointHoverRadius:5,pointBackgroundColor:'#fff',pointBorderWidth:2},{label:'Transaction volume',data:data.volume,borderColor:blue,backgroundColor:'transparent',borderWidth:2,borderDash:[4,4],tension:.35,pointRadius:2}]},cartesian(true));
  make('dashboard-flow','doughnut',{labels:['Deposits','Withdrawals'],datasets:[{data:[data.total_deposits,data.total_withdrawals],backgroundColor:[teal,orange],borderWidth:5,borderColor:'#fff',borderRadius:5}]},donutOptions(),[emptyRing]);
  make('analytics-comparison','bar',{labels:data.labels,datasets:[{label:'Deposits',data:data.deposits,backgroundColor:teal,borderRadius:4,maxBarThickness:26},{label:'Withdrawals',data:data.withdrawals,backgroundColor:orange,borderRadius:4,maxBarThickness:26}]},cartesian(true,true));
  make('analytics-distribution','doughnut',{labels:['Deposits','Withdrawals'],datasets:[{data:[data.deposit_count,data.withdrawal_count],backgroundColor:[teal,orange],borderWidth:5,borderColor:'#fff',borderRadius:5}]},donutOptions(false,true),[emptyRing]);
  make('analytics-trend','line',{labels:data.labels,datasets:[{label:'Transactions',data:data.frequency,borderColor:teal,backgroundColor:'#0ea58c0c',fill:true,borderWidth:2,tension:.3,pointRadius:4,pointBackgroundColor:'#fff',pointBorderWidth:2}]},cartesian(false));
  make('analytics-net','bar',{labels:data.labels,datasets:[{label:'Net cash flow',data:data.net,backgroundColor:data.net.map(x=>x<0?orange:teal),borderRadius:4,maxBarThickness:34}]},cartesian(true));
});
