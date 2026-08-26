'use client'
import {useEffect,useState} from 'react'
export type AuditItem={at:string;action:string;actor:string}
export type DemoState={role:'Public viewer'|'Specialist'|'Counsel';guided:boolean;tourStep:number;exceptions:string[];acknowledgedExceptions:string[];audit:AuditItem[]}
const initial:DemoState={role:'Public viewer',guided:false,tourStep:0,exceptions:['restitution'],acknowledgedExceptions:[],audit:[{at:'2026-08-25 14:32',action:'Restitution review escalated',actor:'Synthetic specialist'},{at:'2026-08-25 13:05',action:'Collector ranking recalculated',actor:'PMOS rules engine'}]}
function restore(saved:string):DemoState{
 const parsed=JSON.parse(saved) as Partial<DemoState>
 return {...initial,...parsed,tourStep:Number.isInteger(parsed.tourStep)?Math.max(0,parsed.tourStep as number):0,exceptions:Array.isArray(parsed.exceptions)?parsed.exceptions:initial.exceptions,acknowledgedExceptions:Array.isArray(parsed.acknowledgedExceptions)?parsed.acknowledgedExceptions:[],audit:Array.isArray(parsed.audit)?parsed.audit:initial.audit}
}
export function useDemoState(){
 const [state,setState]=useState<DemoState>(initial)
 const [hydrated,setHydrated]=useState(false)
 useEffect(()=>{try{const saved=localStorage.getItem('pmos-demo-v1');if(saved)setState(restore(saved))}catch{}finally{setHydrated(true)}},[])
 useEffect(()=>{if(!hydrated)return;try{localStorage.setItem('pmos-demo-v1',JSON.stringify(state))}catch{}},[hydrated,state])
 const log=(action:string)=>setState(s=>({...s,audit:[{at:new Date().toISOString().slice(0,16).replace('T',' '),action,actor:s.role},...s.audit]}))
 return {state,setState,log}
}
