'use client'
export default function ErrorPage({reset}:{reset:()=>void}){return <main className="statePage"><h1>PMOS could not load this view.</h1><p>No data was changed. Retry the public demonstration.</p><button onClick={reset}>Try again</button></main>}
