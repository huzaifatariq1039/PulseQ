import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Router } from '@angular/router';
import { catchError, throwError, EMPTY } from 'rxjs';
import { environment } from '../../../environments/environment';

/**
 * Helper to determine the correct auth page based on current URL.
 */
function getAuthPageForUrl(url: string): string {
  const cleanUrl = url.split('?')[0].split('#')[0];
  if (cleanUrl.startsWith('/staff/admin')) {
    return '/staff/admin/auth';
  } else if (cleanUrl.startsWith('/staff/doctor')) {
    return '/staff/doctor/auth';
  } else if (cleanUrl.startsWith('/staff/reception')) {
    return '/staff/reception/auth';
  } else if (cleanUrl.startsWith('/staff/pharmacy')) {
    return '/staff/pharmacy/auth';
  } else if (cleanUrl.startsWith('/patient')) {
    return '/patient/auth';
  }
  return '/patient/auth';
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const platformId = inject(PLATFORM_ID);
  const isBrowser = isPlatformBrowser(platformId);
  const router = inject(Router);

  let apiReq = req;

  // rewrite relative /api URLs to the absolute backend URL on server
  if (!isBrowser && req.url.startsWith('/api')) {
    const absoluteUrl = `${environment.apiBaseUrl}${req.url.replace('/api/v1', '')}`;
    apiReq = req.clone({ url: absoluteUrl });
  }

  // Only attach token to our own API calls
  const isApiRequest = apiReq.url.startsWith('/api') ||
    apiReq.url.includes(environment.apiBaseUrl.replace('/api/v1', ''));

  if (!isApiRequest) {
    return next(apiReq);
  }

  // Attempt to retrieve token (only in browser)
  let token: string | null = null;
  try {
    if (isBrowser) {
      token = localStorage.getItem('pulseq_token');
    }
  } catch { /* SSR-safe */ }

  // Clone with token if available
  let clonedReq = apiReq;
  if (token) {
    clonedReq = apiReq.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`
      }
    });
  }

  // Attach error handling to ALL requests (whether token was present or not)
  // This prevents unhandled 401s from crashing the SSR render
  return next(clonedReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401) {
        if (isBrowser) {
          // Browser: clear storage and navigate to auth page
          try {
            localStorage.removeItem('pulseq_token');
            localStorage.removeItem('pulseq_user');
            localStorage.removeItem('hospitalId');
            localStorage.removeItem('doctorId');
          } catch (e) {
            console.error('Failed to clear localStorage:', e);
          }
          const redirectPath = getAuthPageForUrl(window.location.pathname);
          router.navigate([redirectPath]).catch(err => {
            console.error(`Navigation to ${redirectPath} failed:`, err);
          });
          console.warn(`401 Unauthorized - Redirecting to ${redirectPath}`, error);
        } else {
          // Server: swallow the 401 error to prevent SSR render failure
          console.warn(`[SSR] Received 401 on server request, suppressing to prevent render failure:`, error.url);
          return EMPTY;
        }
      }
      return throwError(() => error);
    })
  );
};
