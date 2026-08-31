import { env } from '$env/dynamic/private';
import { PrimerApi } from '$lib/api/client';

/**
 * The server's connection to Control.
 *
 * The browser never reaches Control directly. Requests pass through this
 * server, which forwards the identity headers the edge proxy set. If a
 * browser could call Control itself, it could set those headers itself and
 * be anyone.
 */
export function apiFor(request: Request, fetch: typeof globalThis.fetch): PrimerApi {
	const forwarded = new Headers();
	for (const name of [
		'x-auth-request-user',
		'x-auth-request-email',
		'x-auth-request-groups',
		'x-request-id',
	]) {
		const value = request.headers.get(name);
		if (value) forwarded.set(name, value);
	}

	return new PrimerApi({
		baseUrl: env.PRIMER_CONTROL_URL ?? 'http://localhost:8000',
		fetch: (input, init = {}) => {
			const headers = new Headers(init.headers);
			for (const [name, value] of forwarded) headers.set(name, value);
			return fetch(input, { ...init, headers });
		},
	});
}
