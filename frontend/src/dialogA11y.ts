import { useEffect, useRef } from 'react'

/** Shared keyboard and focus behaviour for the existing animated dialogs. */
export function useDialogA11y(active: boolean, onClose: () => void) {
  const ref=useRef<HTMLDivElement>(null)
  const closeRef=useRef(onClose)
  closeRef.current=onClose
  useEffect(()=>{
    if(!active)return
    const dialog=ref.current
    if(!dialog)return
    const previous=document.activeElement instanceof HTMLElement?document.activeElement:null
    const focusable=()=>Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), [contenteditable="true"], [role="combobox"]:not([data-disabled]), a[href], summary')).filter(element=>element.getClientRects().length>0)
    if(!dialog.contains(document.activeElement)) (focusable()[0]||dialog).focus()
    const keydown=(event:KeyboardEvent)=>{
      const roots=Array.from(document.querySelectorAll<HTMLElement>('[data-dialog-root]'))
      const topmost=roots[roots.length-1]
      if(topmost&&topmost!==dialog)return
      if(document.querySelector('[role="listbox"][data-state="open"]'))return
      if(event.key==='Escape'){event.preventDefault();if(closeRef.current)closeRef.current();return}
      if(event.key!=='Tab')return
      const items=focusable()
      if(!items.length){event.preventDefault();dialog.focus();return}
      const first=items[0],last=items[items.length-1]
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
    }
    document.addEventListener('keydown',keydown)
    return()=>{document.removeEventListener('keydown',keydown);previous?.focus()}
  },[active])
  return ref
}
