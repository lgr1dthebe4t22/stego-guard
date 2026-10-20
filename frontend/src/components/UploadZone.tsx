// Зона загрузки документа: drag&drop + клик. Принимает PNG/JPEG.
import { useState } from 'react';
import { Group, Text } from '@mantine/core';
import { Dropzone, type FileRejection } from '@mantine/dropzone';

interface Props {
  onFile: (file: File) => void;
}

export default function UploadZone({ onFile }: Props) {
  const [rejected, setRejected] = useState('');

  const handleReject = (files: FileRejection[]) => {
    setRejected(
      files[0]?.errors[0]?.code === 'file-invalid-type'
        ? 'Нужен PNG или JPEG'
        : 'Файл не подходит',
    );
  };

  return (
    <div>
      <Dropzone
        onDrop={(files) => {
          setRejected('');
          onFile(files[0]);
        }}
        onReject={handleReject}
        accept={{ 'image/png': ['.png'], 'image/jpeg': ['.jpeg', '.jpg'] }}
        maxFiles={1}
        multiple={false}
        styles={{
          root: { backgroundColor: 'transparent' },
        }}
      >
        <Group justify="center" gap="sm" style={{ pointerEvents: 'none' }}>
          <Text size="xl">📄</Text>
          <div>
            <Text size="lg" inline>
              Перетащите документ сюда
            </Text>
            <Text size="sm" c="dimmed" inline>
              {' '}или кликните для выбора (PNG / JPEG)
            </Text>
          </div>
        </Group>
      </Dropzone>
      {rejected && (
        <Text c="red" size="sm" mt="xs">
          {rejected}
        </Text>
      )}
    </div>
  );
}