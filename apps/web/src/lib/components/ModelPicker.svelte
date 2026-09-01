<script lang="ts">
	import { Cpu } from '@lucide/svelte';
	import { DropdownMenu } from '@sivir-ui/svelte';

	interface Props {
		models: { id: string; default: boolean }[];
		/** Empty means the deployment's default. */
		value?: string;
	}

	let { models, value = $bindable('') }: Props = $props();

	let chosen = $derived(models.find((model) => model.id === value));
	let fallback = $derived(models.find((model) => model.default) ?? models[0]);
	let shown = $derived(chosen ?? fallback);
</script>

<!--
  Hidden entirely when there is nothing to choose between. A picker with one
  option is a control that does nothing, and most deployments serve one model.
-->
{#if models.length > 1}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger variant="ghost" size="sm" class="text-muted-foreground">
			<Cpu size={14} aria-hidden="true" />
			<span class="max-w-[12rem] truncate" title={shown?.id}>{shown?.id ?? 'Default'}</span>
		</DropdownMenu.Trigger>
		<DropdownMenu.Content>
			<DropdownMenu.RadioGroup {value} onValueChange={(next) => (value = next)}>
				{#each models as model (model.id)}
					<DropdownMenu.RadioItem value={model.id}>
						<span class="flex w-full items-center justify-between gap-4">
							<span class="truncate">{model.id}</span>
							{#if model.default}
								<span class="text-xs text-muted-foreground">Default</span>
							{/if}
						</span>
					</DropdownMenu.RadioItem>
				{/each}
			</DropdownMenu.RadioGroup>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{/if}
