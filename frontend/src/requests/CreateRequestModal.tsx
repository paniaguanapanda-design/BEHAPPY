import React, { useState } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, uploadRequestPhoto } from "@/src/api";
import { CATEGORIES, useI18n } from "@/src/i18n";
import { queryClient } from "@/src/query-client";
import { useToast } from "@/src/toast";
import { useTheme } from "@/src/theme";
import { Button } from "@/src/ui";
import { useRequestStyles } from "./styles";
import type { PhotoAsset, Zone } from "./types";

/** Modal para publicar una solicitud: titulo, oficio, descripcion y hasta 4 fotos (se reducen a 1600 px). */
export function CreateRequestModal({ visible, zone, onClose, onCreated }: {
  visible: boolean;
  zone?: Zone;
  onClose: () => void;
  onCreated: () => void;
}) {
  const styles = useRequestStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { t } = useI18n();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const [photos, setPhotos] = useState<PhotoAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const canPublish = !!zone?.province && zone.lat != null && zone.lng != null;

  const close = () => {
    if (busy) return;
    setTitle("");
    setDescription("");
    setPhotos([]);
    onClose();
  };
  const choosePhotos = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsMultipleSelection: true,
        selectionLimit: 4 - photos.length,
        quality: 0.85,
      });
      if (!result.canceled) setPhotos((current) => [...current, ...result.assets].slice(0, 4));
    } catch (error: any) {
      toast(error?.message || t("error_generic"), "error");
    }
  };
  const publish = async () => {
    if (!title.trim() || !description.trim() || !canPublish) return toast(t("required"), "error");
    setBusy(true);
    try {
      const paths: string[] = [];
      for (const photo of photos) {
        const image = ImageManipulator.manipulate(photo.uri);
        if (photo.width >= photo.height && photo.width > 1600) image.resize({ width: 1600 });
        else if (photo.height > 1600) image.resize({ height: 1600 });
        const jpeg = await (await image.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: 0.82 });
        paths.push(await uploadRequestPhoto(jpeg.uri, "image/jpeg"));
      }
      await api("/requests/board", { body: { title: title.trim(), description: description.trim(), category, photos: paths } });
      queryClient.invalidateQueries({ queryKey: ["marketplace-requests"] });
      toast(t("requests_published"));
      setTitle("");
      setDescription("");
      setPhotos([]);
      onCreated();
    } catch (error: any) {
      toast(error?.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={close}>
      <KeyboardAvoidingView style={styles.modalRoot} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={[styles.modalHeader, { paddingTop: insets.top + 8 }]}>
          <Pressable onPress={close} style={styles.modalBack}><Ionicons name="close" size={23} color={colors.onSurface} /></Pressable>
          <Text style={styles.modalTitle}>{t("requests_new_title")}</Text>
          <View style={{ width: 42 }} />
        </View>
        <ScrollView contentContainerStyle={[styles.modalBody, { paddingBottom: insets.bottom + 28 }]} keyboardShouldPersistTaps="handled">
          <View style={styles.privacyNotice}>
            <Ionicons name="shield-checkmark-outline" size={18} color={colors.brandTertiary} />
            <Text style={styles.privacyNoticeText}>{t("requests_privacy_notice")}</Text>
          </View>
          <Text style={styles.fieldLabel}>{t("requests_work_title")}</Text>
          <TextInput testID="request-title-input" value={title} onChangeText={setTitle} maxLength={120} placeholder={t("requests_title_placeholder")} placeholderTextColor={colors.muted} style={styles.input} />
          <Text style={styles.fieldLabel}>{t("category")}</Text>
          <View style={styles.categoryOptions}>
            {CATEGORIES.map((item) => {
              const active = category === item;
              return (
                <Pressable key={item} onPress={() => setCategory(item)} style={[styles.categoryOption, active && styles.categoryOptionOn]}>
                  <Text style={[styles.categoryOptionText, active && styles.categoryOptionTextOn]}>{t(`cat_${item}`)}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.fieldLabel}>{t("requests_description")}</Text>
          <TextInput testID="request-description-input" value={description} onChangeText={setDescription} multiline maxLength={2000} placeholder={t("requests_description_placeholder")} placeholderTextColor={colors.muted} textAlignVertical="top" style={[styles.input, styles.descriptionInput]} />
          <View style={styles.photoLabelRow}>
            <Text style={styles.fieldLabel}>{t("requests_photos")}</Text>
            <Text style={styles.photoLimit}>{photos.length}/4</Text>
          </View>
          <View style={styles.photoPickerRow}>
            {photos.map((photo, index) => (
              <View key={`${photo.uri}-${index}`} style={styles.selectedPhoto}>
                <Image source={{ uri: photo.uri }} style={styles.selectedPhotoImage} />
                <Pressable onPress={() => setPhotos((current) => current.filter((_, i) => i !== index))} style={styles.removePhoto}>
                  <Ionicons name="close" size={14} color={colors.onSurfaceInverse} />
                </Pressable>
              </View>
            ))}
            {photos.length < 4 ? (
              <Pressable testID="request-add-photo" onPress={() => void choosePhotos()} style={styles.addPhoto}>
                <Ionicons name="camera-outline" size={22} color={colors.brandTertiary} />
                <Text style={styles.addPhotoText}>{t("add_photo")}</Text>
              </Pressable>
            ) : null}
          </View>
          <View style={styles.locationNotice}>
            <Ionicons name="location" size={16} color={colors.brandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.locationTitle}>{t("requests_location_label")}</Text>
              <Text style={styles.locationSub}>{zone?.province?.name ?? t("requests_location_missing")}</Text>
            </View>
            <Text style={styles.approximate}>{t("requests_approx_only")}</Text>
          </View>
          <Text style={styles.privacyFootnote}>{t("requests_no_contact_shared")}</Text>
          <Button testID="request-publish-submit" title={t("requests_publish")} icon="paper-plane-outline" loading={busy} disabled={!canPublish || !title.trim() || !description.trim()} onPress={() => void publish()} />
        </ScrollView>
      </KeyboardAvoidingView>
    </Modal>
  );
}
