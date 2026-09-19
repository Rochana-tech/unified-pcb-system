const tbody=document.querySelector("#datasetTable tbody");
const rowCount=document.querySelector("#rowCount");

function parseCSV(text){
  const lines=text.trim().split(/\r?\n/);
  if(!lines.length) return [];
  const headers=lines[0].split(",");
  return lines.slice(1).map(line=>{
    const values=line.split(",");
    const obj={};
    headers.forEach((h,i)=>obj[h]=values[i]??"");
    return obj;
  });
}

fetch("electronics_pcb_synthetic.csv")
  .then(r=>{
    if(!r.ok) throw new Error("Dataset could not be loaded");
    return r.text();
  })
  .then(text=>{
    const rows=parseCSV(text);
    rowCount.textContent=`${rows.length.toLocaleString()} dataset rows`;
    rows.slice(0,10).forEach(r=>{
      const tr=document.createElement("tr");
      ["current","temperature","vibration","rpm","fault_type"].forEach(k=>{
        const td=document.createElement("td");
        td.textContent=r[k] ?? "";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  })
  .catch(err=>{
    rowCount.textContent="Dataset preview unavailable";
    const tr=document.createElement("tr");
    const td=document.createElement("td");
    td.colSpan=5;
    td.textContent=err.message;
    tr.appendChild(td);
    tbody.appendChild(tr);
  });
