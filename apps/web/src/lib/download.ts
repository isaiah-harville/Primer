/**
 * What a proxied document download is allowed to carry back.
 *
 * These are files other people uploaded, served from the application's own
 * origin, so the headers that decide how a browser treats them are a
 * security boundary rather than a formatting detail. Kept here, and pinned
 * by tests, rather than inline in the route.
 */

//: Only what describes the bytes. Everything else Control sets - cookies
//: it might grow, caching directives meant for a service-to-service hop -
//: is dropped rather than passed to a browser that reads them differently.
const DESCRIBES_THE_BYTES = ['content-type', 'content-disposition', 'content-length'];

/**
 * The response headers to hand a browser for a downloaded document.
 *
 * `Content-Disposition` is carried across unchanged rather than rewritten
 * to `inline`. Control sends `attachment`, and it must stay that way:
 * anything the browser agreed to render in place - an uploaded HTML file
 * above all - would run in Primer's own origin, with the session of
 * whoever opened it.
 */
export function downloadHeaders(upstream: Headers): Headers {
	const safe = new Headers();
	for (const name of DESCRIBES_THE_BYTES) {
		const value = upstream.get(name);
		if (value) safe.set(name, value);
	}
	// Which documents a person opened is not something to leave in a shared
	// cache, and a shared cache is exactly what sits in front of this.
	safe.set('cache-control', 'private, no-store');
	return safe;
}
