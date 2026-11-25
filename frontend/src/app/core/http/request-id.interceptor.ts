import { HttpInterceptorFn } from '@angular/common/http';

export const requestIdInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/') || req.headers.has('X-Request-ID')) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { 'X-Request-ID': crypto.randomUUID() } }));
};
