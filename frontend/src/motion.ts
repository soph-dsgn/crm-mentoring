import { useReducedMotion } from 'framer-motion'

export const motionEase = {
  out: [0.23, 1, 0.32, 1] as const,
  inOut: [0.77, 0, 0.175, 1] as const,
}

export const motionTime = { press: 0.14, quick: 0.18, standard: 0.22, modal: 0.25 } as const
// Reserved for a future interruptible drag gesture; routine navigation stays time based.
export const motionSpring = { type: 'spring', duration: 0.5, bounce: 0.2 } as const

export const motionScrollBehavior = (reduced: boolean): ScrollBehavior => reduced ? 'auto' : 'smooth'

export const useCalmMotion = () => {
  const reduced = Boolean(useReducedMotion())
  return {
    reduced,
    modal: {
      initial: { opacity: 0, transform: reduced ? 'none' : 'scale(0.96)' },
      animate: { opacity: 1, transform: 'scale(1)' },
      exit: { opacity: 0, transform: reduced ? 'none' : 'scale(0.96)', transition: { duration: reduced ? 0.12 : motionTime.press, ease: motionEase.inOut } },
      transition: { duration: reduced ? 0.14 : motionTime.modal, ease: motionEase.out },
    },
    backdrop: {
      initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0, transition: { duration: reduced ? 0.12 : motionTime.press, ease: motionEase.inOut } },
      transition: { duration: reduced ? 0.14 : motionTime.modal, ease: motionEase.out },
    },
    popover: {
      initial: { opacity: 0, transform: reduced ? 'none' : 'scale(0.97)' },
      animate: { opacity: 1, transform: 'scale(1)' },
      exit: { opacity: 0, transform: reduced ? 'none' : 'scale(0.97)', transition: { duration: reduced ? 0.1 : motionTime.press, ease: motionEase.inOut } },
      transition: { duration: reduced ? 0.12 : motionTime.quick, ease: motionEase.out },
    },
    tab: { duration: reduced ? 0.01 : motionTime.press, ease: motionEase.inOut },
  }
}
