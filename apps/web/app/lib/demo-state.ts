'use client'
import {useEffect,useState} from 'react'
export type AuditItem={at:string;action:string;actor:string}
type DemoState={role:'Public viewer'|'Specialist'|'Counsel';guided:boolean;exceptions:string[];audit:AuditItem[]}
const initial:DemoState={role:'Public viewer',guided:false,exceptions:['restitution'],audit:[{at:'2026-08-25 14:32',action:'Restitution review escalated',actor:'Synthetic specialist'},{at:'2026-08-25 13:05',action:'Collector ranking recalculated',actor:'PMOS rules engine'}]}
export function useDemoState(){
 const [state,setState]=useState<DemoState>(initial)
 const [hydrated,setHydrated]=useState(false)
 useEffect(()=>{try{const saved=localStorage.getItem('pmos-demo-v1');if(saved)setState(JSON.parse(saved))}catch{}finally{setHydrated(true)}},[])
 useEffect(()=>{if(!hydrated)return;try{localStorage.setItem('pmos-demo-v1',JSON.stringify(state))}catch{}},[hydrated,state])
 const log=(action:string)=>setState(s=>({...s,audit:[{at:new Date().toISOString().slice(0,16).replace('T',' '),action,actor:s.role},...s.audit]}))
 return {state,setState,log}
}
