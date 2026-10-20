// Отображение SHA-256: обрезка по центру + кнопка копирования.
import { useState } from 'react';
import { ActionIcon, Group, Text, Tooltip } from '@mantine/core';

interface Props {
  hash: string;
}

export default function HashDisplay({ hash }: Props) {
  const [copied, setCopied] = useState(false);

  const short = hash
    ? `${hash.slice(0, 12)}…${hash.slice(-8)}`
    : '—';

  const copy = async () => {
    await navigator.clipboard.writeText(hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Group gap="xs">
      <Text size="sm" ff="monospace" c="dimmed">
        SHA-256: {short}
      </Text>
      <Tooltip label={copied ? 'Скопировано!' : 'Копировать'}>
        <ActionIcon variant="subtle" size="sm" onClick={copy} disabled={!hash}>
          {copied ? '✓' : '📋'}
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}