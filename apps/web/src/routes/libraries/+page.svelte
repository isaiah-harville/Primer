<script lang="ts">
	import { enhance } from '$app/forms';
	import { Alert, Badge, Button, Card, Input, Label } from '@sivir-ui/svelte';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();
</script>

<h1 class="text-2xl font-bold">Libraries</h1>

<p class="mt-2 max-w-2xl text-muted-foreground">
	A library is a private collection of sources. Only you can see it, and every question is
	asked of one library at a time.
</p>

<Card.Root class="mt-6">
	<Card.Content>
		<form method="POST" action="?/create" use:enhance class="flex flex-col gap-2">
			<Label for="library-name">New library</Label>
			<div class="flex gap-2">
				<Input
					id="library-name"
					name="name"
					required
					maxlength={120}
					placeholder="Papers on retrieval"
					value={form?.name ?? ''}
					aria-describedby={form?.error ? 'create-error' : undefined}
					aria-invalid={form?.error ? 'true' : undefined}
				/>
				<Button type="submit">Create</Button>
			</div>
			{#if form?.error}
				<div id="create-error">
					<Alert.Root variant="error">
						<Alert.Description>{form.error}</Alert.Description>
					</Alert.Root>
				</div>
			{/if}
		</form>
	</Card.Content>
</Card.Root>

{#if data.libraries.length === 0}
	<p class="mt-8 text-muted-foreground">
		No libraries yet. Create one above to start adding documents.
	</p>
{:else}
	<ul class="mt-8 divide-y divide-border">
		{#each data.libraries as library (library.id)}
			<li class="flex items-center gap-4 py-3">
				<a href="/libraries/{library.id}" class="flex-1 font-semibold hover:underline">
					{library.name}
				</a>
				<Badge variant="secondary">
					{library.document_count}
					{library.document_count === 1 ? 'document' : 'documents'}
				</Badge>
				<!--
				  A confirm step, because deleting a library takes its
				  documents with it and the control sits beside a link.
				-->
				<form
					method="POST"
					action="?/delete"
					use:enhance={({ cancel }) => {
						if (!confirm(`Delete "${library.name}" and everything in it?`)) cancel();
					}}
				>
					<input type="hidden" name="id" value={library.id} />
					<Button type="submit" variant="destructive" size="sm">
						Delete<span class="sr-only"> {library.name}</span>
					</Button>
				</form>
			</li>
		{/each}
	</ul>
{/if}
