import { useEffect, useId, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { TrashIcon, XIcon } from '@phosphor-icons/react'
import { useDialogA11y } from './dialogA11y'
import { useCalmMotion } from './motion'

type DialogProps = {
  open: boolean
  title: string
  description?: string
  children: React.ReactNode
  onClose: () => void
  wide?: boolean
  dismissible?: boolean
}

export function Dialog({open,title,description,children,onClose,wide=false,dismissible=true}:DialogProps) {
  const calm=useCalmMotion()
  const titleId=useId()
  const descriptionId=useId()
  const dialogRef=useDialogA11y(open,dismissible?onClose:()=>{})
  return <AnimatePresence initial={false}>{open&&<motion.div className="modal-backdrop" {...calm.backdrop} onMouseDown={event=>{if(dismissible&&event.target===event.currentTarget)onClose()}}>
    <motion.div ref={dialogRef} data-dialog-root tabIndex={-1} className={`dialog ${wide?'wide':''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description?descriptionId:undefined} {...calm.modal}>
      <div className="dialog-head"><div><h2 id={titleId}>{title}</h2>{description&&<p id={descriptionId}>{description}</p>}</div>{dismissible&&<button type="button" className="icon-btn" aria-label="Закрыть" onClick={onClose}><XIcon size={20} weight="regular"/></button>}</div>
      {children}
    </motion.div>
  </motion.div>}</AnimatePresence>
}

type ConfirmProps = {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  showCancel?: boolean
  onConfirm: () => void | Promise<void>
  onClose: () => void
}

export function ConfirmDialog({open,title,description,confirmLabel='Подтвердить',cancelLabel='Отмена',danger=false,showCancel=true,onConfirm,onClose}:ConfirmProps) {
  const [pending,setPending]=useState(false)
  const pendingRef=useRef(false)
  const [error,setError]=useState('')
  useEffect(()=>{if(open){pendingRef.current=false;setPending(false);setError('')}},[open])
  const runConfirm=async()=>{
    if(pendingRef.current)return
    pendingRef.current=true
    setPending(true);setError('')
    try { await onConfirm(); onClose() }
    catch { setError('Не удалось выполнить действие. Данные не изменены') }
    finally { pendingRef.current=false;setPending(false) }
  }
  return <Dialog open={open} title={title} description={description} onClose={onClose} dismissible={!pending}>
    {error&&<p className="dialog-error" role="alert">{error}</p>}
    <div className="dialog-actions">
      {showCancel&&<button type="button" className="btn secondary" disabled={pending} onClick={onClose}>{cancelLabel}</button>}
      <button type="button" className={`btn ${danger?'danger solid':'primary'}`} disabled={pending} onClick={()=>void runConfirm()}>{danger&&<TrashIcon size={16} weight="regular"/>}{pending?'Сохраняем…':confirmLabel}</button>
    </div>
  </Dialog>
}

export function DeleteConfirmDialog(props:Omit<ConfirmProps,'danger'>) {
  return <ConfirmDialog {...props} danger/>
}

export function NoticeDialog({open,title,description,onClose}:{open:boolean;title:string;description:string;onClose:()=>void}) {
  return <ConfirmDialog open={open} title={title} description={description} confirmLabel="Понятно" showCancel={false} onConfirm={onClose} onClose={onClose}/>
}

export function InputDialog({open,title,label,initialValue='',confirmLabel='Сохранить',onConfirm,onClose}:{open:boolean;title:string;label:string;initialValue?:string;confirmLabel?:string;onConfirm:(value:string)=>void|Promise<void>;onClose:()=>void}) {
  const [value,setValue]=useState(initialValue)
  const [error,setError]=useState('')
  const pendingRef=useRef(false)
  const [pending,setPending]=useState(false)
  const inputId=useId()
  useEffect(()=>{if(open){pendingRef.current=false;setPending(false);setValue(initialValue);setError('')}},[initialValue,open])
  const submit=async(event:React.FormEvent)=>{
    event.preventDefault()
    if(pendingRef.current)return
    const normalized=value.trim()
    if(!normalized){setError('Введите название');return}
    pendingRef.current=true;setPending(true)
    try { await onConfirm(normalized);onClose() } catch { setError('Не удалось сохранить. Попробуйте ещё раз') }
    finally { pendingRef.current=false;setPending(false) }
  }
  return <Dialog open={open} title={title} onClose={onClose}>
    <form className="form" onSubmit={event=>void submit(event)}>
      <label className="field" htmlFor={inputId}><span>{label}</span><input id={inputId} autoFocus value={value} onChange={event=>setValue(event.target.value)}/></label>
      {error&&<p className="dialog-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="btn secondary" disabled={pending} onClick={onClose}>Отмена</button><button className="btn primary" type="submit" disabled={pending}>{pending?'Сохраняем…':confirmLabel}</button></div>
    </form>
  </Dialog>
}
