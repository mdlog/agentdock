import Avatar from "boring-avatars";
import { useEffect, useState } from "react";

const colors = ["#0F766E", "#14B8A6", "#FACC15", "#F8FAFC", "#172033"];

export const AgentAvatar = ({ name, size = 42, testId, className = "", src }: { name:string; size?:number; testId?:string; className?:string; src?:string }) => {
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[src]);
  return <div className={`agent-icon ${className}`} style={{ width:size, height:size, flexBasis:size }} data-testid={testId} aria-label={`${name} icon`}>
    {src&&!failed?<img src={src} alt="" loading="lazy" onError={()=>setFailed(true)}/>:<Avatar size={size} name={name} variant="beam" colors={colors} square />}
  </div>;
};