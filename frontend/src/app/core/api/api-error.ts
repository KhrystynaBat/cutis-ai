import { HttpErrorResponse } from '@angular/common/http';

export interface ApiErrorBody {
  code: string;
  message: string;
  correlationId?: string;
  details?: { msg?: string }[];
}

export function parseApiError(err: unknown): ApiErrorBody {
  if (err instanceof HttpErrorResponse) {
    const body = err.error?.error as ApiErrorBody | undefined;
    if (body?.code) {
      const detail = body.details?.find((d) => typeof d.msg === 'string')?.msg;
      return detail ? { ...body, message: detail.replace(/^Value error, /, '') } : body;
    }
    if (err.status === 0) {
      return { code: 'NETWORK', message: 'Сервер недоступний' };
    }
    return { code: `HTTP_${err.status}`, message: err.statusText || 'Помилка запиту' };
  }
  return { code: 'UNKNOWN', message: 'Невідома помилка' };
}
