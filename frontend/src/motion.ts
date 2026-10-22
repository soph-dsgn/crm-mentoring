import { useReducedMotion } from 'framer-motion'

export const motionEase = {
  out: [0.23, 1, 0.32, 1] as const,
  inOut: [0.77, 0, 0.175, 1] as const,
}

export const motionTime = { press: 0.14, quick: 0.18, standard: 0.22, modal: 0.25 } as const
// Reserved for a future interruptible drag gesture; routine navigation stays time based.
export const motionSpring = { type: 'spring', duration: 0.5, bounce: 0.2 } as const

export const useCalmMotion = () => {
  const reduced = Boolean(useReducedMotion())
  const canHover = !reduced && typeof window !== 'undefined' && window.matchMedia('(hover: hover) and (pointer: fine)').matches
  return {
    reduced,
    canHover,
    page: {
      initial: { opacity: 0, transform: reduced ? 'none' : 'translateY(8px)' },
      animate: { opacity: 1, transform: 'translateY(0px)' },
      exit: { opacity: 0, transform: reduced ? 'none' : 'translateY(-4px)' },
      transition: { duration: reduced ? 0.12 : motionTime.standard, ease: motionEase.out },
    },
    list: {
      initial: { opacity: 0, transform: reduced ? 'none' : 'translateY(6px)' },
      animate: { opacity: 1, transform: 'translateY(0px)' },
      exit: { opacity: 0, transform: reduced ? 'none' : 'translateY(-4px)' },
      transition: { duration: reduced ? 0.12 : motionTime.quick, ease: motionEase.out },
    },
    modal: {
      initial: { opacity: 0, transform: reduced ? 'none' : 'scale(0.96)' },
      animate: { opacity: 1, transform: 'scale(1)' },
      exit: { opacity: 0, transform: reduced ? 'none' : 'scale(0.96)' },
      transition: { duration: reduced ? 0.14 : motionTime.modal, ease: motionEase.out },
    },
    backdrop: {
      initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 },
      transition: { duration: reduced ? 0.14 : motionTime.modal, ease: motionEase.out },
    },
    popover: {
      initial: { opacity: 0, transform: reduced ? 'none' : 'scale(0.97)' },
      animate: { opacity: 1, transform: 'scale(1)' },
      exit: { opacity: 0, transform: reduced ? 'none' : 'scale(0.97)' },
      transition: { duration: reduced ? 0.12 : motionTime.quick, ease: motionEase.out },
    },
    collapse: {
      initial: { height: 0, opacity: 0 }, animate: { height: 'auto', opacity: 1 }, exit: { height: 0, opacity: 0 },
      transition: { duration: reduced ? 0.12 : motionTime.standard, ease: motionEase.out },
    },
    tab: { duration: reduced ? 0.01 : motionTime.standard, ease: motionEase.inOut },
    layout: { duration: reduced ? 0.01 : motionTime.standard, ease: motionEase.inOut },
  }
}
