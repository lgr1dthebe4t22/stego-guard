// Карточка результата: вердикт проверки ИЛИ результат защиты.
import { Alert, Button, Group, Paper, Stack, Text } from '@mantine/core';
import type { EmbedResult, VerifyResponse } from '../types/api';
import HashDisplay from './HashDisplay';

type Props =
  | { kind: 'verify'; result: VerifyResponse }
  | { kind: 'embed'; result: EmbedResult; fileName: string };

const STATUS_STYLE: Record<string, { color: string; emoji: string; label: string }> = {
  AUTHENTIC: { color: 'green', emoji: '✅', label: 'Подлинный документ' },
  TAMPERED: { color: 'red', emoji: '🔴', label: 'Обнаружено вмешательство' },
  NO_WATERMARK: { color: 'yellow', emoji: '🟡', label: 'Метка не найдена — документ не защищён системой' },
};

export default function ResultCard(props: Props) {
  if (props.kind === 'embed') {
    const { result, fileName } = props;

    // скачивание программное: никакой <a>, никакого перетаскивания браузером
    const download = () => {
      const url = URL.createObjectURL(result.blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `protected_${fileName}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };

    return (
      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          <Alert color="green" title="Документ защищён" icon="🔒">
            Метка внедрена (код содержимого + ID). Скачайте защищённую копию.
          </Alert>
          <HashDisplay hash={result.sha256} />
          <Text size="sm" c="dimmed">Защитил: {result.userId}</Text>
          <Group>
            <Button onClick={download} leftSection="⬇">
              Скачать защищённый файл
            </Button>
          </Group>
        </Stack>
      </Paper>
    );
  }

  const { result } = props;
  const style = STATUS_STYLE[result.status] ?? {
    color: 'gray', emoji: '❓', label: result.status,
  };
  const heatmapUrl = result.heatmap_base64
    ? `data:image/png;base64,${result.heatmap_base64}`
    : null;

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Alert color={style.color} title={`${style.emoji} ${style.label}`}>
          {result.status === 'AUTHENTIC' && (
            <>BER = 0 — метка цела, код содержимого совпал{result.user_id ? ` (защитил: ${result.user_id})` : ''}.</>
          )}
          {result.status === 'TAMPERED' && (
            <>BER = {result.ber.toFixed(4)} — копии метки разошлись, содержимое изменено.</>
          )}
        </Alert>
        <HashDisplay hash={result.sha256} />
        {heatmapUrl && (
          <div>
            <Text size="sm" fw={500} mb="xs">Тепловая карта вмешательства:</Text>
            <img
              src={heatmapUrl}
              alt="Тепловая карта зон изменений"
              style={{ maxWidth: '100%', borderRadius: 8 }}
            />
          </div>
        )}
      </Stack>
    </Paper>
  );
}