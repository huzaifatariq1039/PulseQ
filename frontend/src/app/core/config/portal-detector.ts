/**
 * Portal Detector - Runtime determination of which portal is active
 * 
 * This utility determines which portal should be loaded based on:
 * 1. The current hostname (e.g., patient.pulseq.health, doctor.pulseq.health)
 * 2. Or the URL path if on a multi-portal domain
 * 3. Defaults to 'main' if no portal is detected
 * 
 * This enables a single build artifact to serve multiple portal applications
 * from different subdomains or paths.
 * 
 * ⚠️ SSR-Safe: Returns 'main' immediately if window is not defined (server-side)
 */

export type PortalType = 'main' | 'patient' | 'doctor' | 'pharmacy' | 'reception' | 'admin' | 'demo';

export function detectPortal(): PortalType {
  if (typeof window === 'undefined') {
    return 'main';
  }

  try {
    const hostname = window.location.hostname.toLowerCase();
    const pathname = window.location.pathname;

    const subdomainMap: Record<string, PortalType> = {
      'patient': 'patient',
      'doctor': 'doctor',
      'pharmacy': 'pharmacy',
      'reception': 'reception',
      'admin': 'admin',
      'demo': 'demo'
    };

    // ✅ FIX: Loop through ALL hostname parts, not just parts[0]
    // admin.pulseq.health → checks 'admin', 'pulseq', 'health' → finds 'admin' ✅
    const parts = hostname.split('.');
    for (const part of parts) {
      if (part in subdomainMap) {
        return subdomainMap[part];
      }
    }

    // Path-based detection for localhost
    const pathSegments = pathname.split('/').filter(s => s.length > 0);

    if (pathSegments.length === 0) return 'main';

    const firstSegment = pathSegments[0].toLowerCase();

    if (firstSegment in subdomainMap) {
      return subdomainMap[firstSegment];
    }

    // /staff/admin now returns 'admin' instead of 'main'
    if (firstSegment === 'staff') {
      const secondSegment = pathSegments[1]?.toLowerCase();
      if (secondSegment && secondSegment in subdomainMap) {
        return subdomainMap[secondSegment];
      }
      return 'main';
    }

    return 'main';
  } catch (error) {
    console.warn('Error detecting portal, defaulting to main:', error);
    return 'main';
  }
}

export function getPortalName(): string {
  return detectPortal();
}

export function isPortal(portal: PortalType): boolean {
  return detectPortal() === portal;
}

export function logPortalDetection(): void {
  if (typeof window !== 'undefined') {
    const portal = detectPortal();
    const hostname = window.location.hostname;
    const pathname = window.location.pathname;
    console.log(`[Portal Detection] hostname=${hostname}, pathname=${pathname}, portal=${portal}`);
  }
}