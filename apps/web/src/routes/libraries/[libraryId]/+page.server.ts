import { error, fail } from '@sveltejs/kit';
import { ApiError } from '$lib/api/client';
import { apiFor } from '$lib/server/api';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, parent, request, fetch }) => {
	try {
		// The library comes from the list the layout already fetched, so
		// opening a document list does not re-fetch every library to name one.
		const [{ libraries }, documents] = await Promise.all([
			parent(),
			apiFor(request, fetch).documents(params.libraryId),
		]);
		const library = libraries.find((candidate) => candidate.id === params.libraryId);
		// The server already answered 404 for a library that is not ours;
		// this covers the narrow case of it being deleted between calls.
		if (!library) error(404, 'Library not found');
		return { library, documents };
	} catch (cause) {
		if (cause instanceof ApiError) error(cause.status, cause.message);
		throw cause;
	}
};

export const actions: Actions = {
	reindex: async ({ params, request, fetch }) => {
		const form = await request.formData();
		try {
			await apiFor(request, fetch).reindex(params.libraryId, String(form.get('id')));
		} catch (cause) {
			if (cause instanceof ApiError) return fail(cause.status, { error: cause.message });
			throw cause;
		}
		return { reindexed: true };
	},

	delete: async ({ params, request, fetch }) => {
		const form = await request.formData();
		try {
			await apiFor(request, fetch).deleteDocument(params.libraryId, String(form.get('id')));
		} catch (cause) {
			if (cause instanceof ApiError) return fail(cause.status, { error: cause.message });
			throw cause;
		}
		return { deleted: true };
	},
};
