import { detectPortal } from '../config/portal-detector';

/**
 * Build a router link for a pharmacy page.
 *
 * The pharmacy portal is served in two shapes:
 *  - Subdomain deploy (e.g. pharmacy.pulseq.health): pharmacyRoutes are mounted
 *    at the domain root, so links are bare ("/credits").
 *  - Multi-portal / dev ("main") and during SSR: pharmacy routes are nested in
 *    mainRoutes under "/staff/pharmacy", so links need that prefix.
 *
 * The prefix is derived from detectPortal() — the SAME function that selects the
 * active route table in app.routes.ts — so generated links always match the
 * routes that are actually registered. This is critical for SSR, where `window`
 * is undefined: detectPortal() returns 'main', and so must this helper, otherwise
 * the server-rendered links fail to match (NG04002).
 */
export function pharmacyPath(path: string): string {
    const base = detectPortal() === 'pharmacy' ? '' : '/staff/pharmacy';
    const clean = path.startsWith('/') ? path.slice(1) : path;
    return `${base}/${clean}`;
}

/**
 * Build a router link for a patient page. Same idea as pharmacyPath: on the
 * patient subdomain the routes are at the domain root (bare), otherwise (main/dev
 * and SSR) they're nested under "/patient". Using detectPortal() keeps these links
 * consistent with the registered route table — avoids NG04002 during SSR that the
 * old relative "../x" links caused.
 */
export function patientPath(path: string): string {
    const base = detectPortal() === 'patient' ? '' : '/patient';
    const clean = path.startsWith('/') ? path.slice(1) : path;
    return `${base}/${clean}`;
}
