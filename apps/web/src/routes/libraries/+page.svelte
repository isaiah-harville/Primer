<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();
</script>

<h1>Libraries</h1>

<p class="lead">
	A library is a private collection of sources. Only you can see it, and every question is
	asked of one library at a time.
</p>

<form method="POST" action="?/create" use:enhance class="create">
	<label for="library-name">New library</label>
	<div class="row">
		<input
			id="library-name"
			name="name"
			required
			maxlength="120"
			placeholder="Papers on retrieval"
			value={form?.name ?? ''}
			aria-describedby={form?.error ? 'create-error' : undefined}
			aria-invalid={form?.error ? 'true' : undefined}
		/>
		<button type="submit">Create</button>
	</div>
	{#if form?.error}
		<p id="create-error" class="error" role="alert">{form.error}</p>
	{/if}
</form>

{#if data.libraries.length === 0}
	<p class="empty">No libraries yet. Create one above to start adding documents.</p>
{:else}
	<ul class="libraries">
		{#each data.libraries as library (library.id)}
			<li>
				<a href="/libraries/{library.id}">{library.name}</a>
				<span class="count">
					{library.document_count}
					{library.document_count === 1 ? 'document' : 'documents'}
				</span>
				<!--
				  A confirm dialog, because deleting a library takes its
				  documents with it and the button sits next to a link.
				-->
				<form
					method="POST"
					action="?/delete"
					use:enhance={({ cancel }) => {
						if (!confirm(`Delete "${library.name}" and everything in it?`)) cancel();
					}}
				>
					<input type="hidden" name="id" value={library.id} />
					<button type="submit" class="danger">Delete<span class="visually-hidden"> {library.name}</span></button>
				</form>
			</li>
		{/each}
	</ul>
{/if}

<style>
	.lead {
		color: #475569;
		max-width: 42rem;
	}
	.create {
		margin: 1.5rem 0 2rem;
	}
	.row {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.375rem;
	}
	input {
		flex: 1;
		max-width: 26rem;
		padding: 0.5rem 0.625rem;
		border: 1px solid #cbd5e1;
		border-radius: 8px;
		font: inherit;
	}
	button {
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		border: 1px solid #cbd5e1;
		background: #f8fafc;
		font: inherit;
		cursor: pointer;
	}
	.danger {
		color: #b91c1c;
	}
	.error {
		color: #b91c1c;
		font-size: 0.875rem;
	}
	.empty {
		color: #475569;
	}
	.libraries {
		list-style: none;
		padding: 0;
	}
	.libraries li {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 0;
		border-top: 1px solid #e2e8f0;
	}
	.libraries a {
		font-weight: 600;
		flex: 1;
	}
	.count {
		color: #475569;
		font-size: 0.875rem;
	}
	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}
</style>
