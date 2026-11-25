export const MAX_UPLOAD_MB = 10;
export const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
export const ACCEPT_ATTR = '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp';
const EXTENSIONS = /\.(jpe?g|png|webp)$/i;

export function checkImageFile(file: File): string | null {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type) && !EXTENSIONS.test(file.name)) {
    return 'Підтримуються лише зображення JPG, PNG або WebP';
  }
  if (file.size === 0) {
    return 'Файл порожній';
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `Файл завеликий: максимум ${MAX_UPLOAD_MB} МБ`;
  }
  return null;
}

export function loadPreview(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(url);
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('decode'));
    };
    img.src = url;
  });
}
