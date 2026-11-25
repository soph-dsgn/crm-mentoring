import type { Student } from './types'

export default function Avatar({ student, size = 'md', className = '' }: { student: Student; size?: 'sm'|'md'|'lg'|'xl'; className?: string }) {
  const index = Math.max(0, student.avatarIndex % 16)
  const photo = /^data:image\/(?:jpeg|png|webp);base64,[a-z0-9+/=]+$/i.test(student.photo) ? student.photo : ''
  if (!photo && student.avatarIndex < 0) return <span className={`photo-avatar avatar-initials avatar-${size} ${className}`} role="img" aria-label={`Аватар: ${student.name}`}>{student.name.slice(0,1)||'+'}</span>
  const style = photo
    ? { backgroundImage: `url(${photo})`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : { backgroundImage: 'url(/demo-portraits.png)', backgroundSize: '400% 400%', backgroundPosition: `${index % 4 * 100 / 3}% ${Math.floor(index / 4) * 100 / 3}%` }
  return <span className={`photo-avatar avatar-${size} ${className}`} style={style} role="img" aria-label={`Фото: ${student.name}`} />
}

export async function imageFromFile(file: File): Promise<string> {
  if (!['image/jpeg', 'image/png'].includes(file.type)) throw new Error('Выберите файл JPG или PNG')
  if (file.size > 12 * 1024 * 1024) throw new Error('Фото должно быть меньше 12 МБ')
  const image = await createImageBitmap(file)
  const scale = Math.min(1, 480 / Math.max(image.width, image.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(image.width * scale)
  canvas.height = Math.round(image.height * scale)
  canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height)
  image.close()
  const photo = canvas.toDataURL('image/jpeg', .78)
  if (photo.length > 256_000) throw new Error('Выберите изображение меньшего размера')
  return photo
}
