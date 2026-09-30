// MORPHRIG: code side facial control (sliders, presets, visemes, blink, gaze). Output is FOperativeFaceState,
// which the anim proxy adds on top of the face bones and morph curves that the playing clip animates.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OperativeTypes.h"
#include "OperativeFaceComponent.generated.h"

class UOperativeLibrary;

UCLASS(ClassGroup = (Operative), meta = (BlueprintSpawnableComponent))
class MORPHRIG_API UOperativeFaceComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UOperativeFaceComponent();

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	// --- sliders (code layer, normalised 0..1)
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetMorph(FName Name, float Value);
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") float GetMorph(FName Name) const;
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetViseme(FName Name, float Value);
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") float GetViseme(FName Name) const;
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetJawOpen(float Value) { JawSlider = FMath::Clamp(Value, 0.f, 1.f); }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") float GetJawOpen() const { return JawSlider; }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetTongueLift(float Value) { TongueSlider = FMath::Clamp(Value, 0.f, 1.f); }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") float GetTongueLift() const { return TongueSlider; }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetBlinkSliders(float Left, float Right) { BlinkSliderL = FMath::Clamp(Left, 0.f, 1.f); BlinkSliderR = FMath::Clamp(Right, 0.f, 1.f); }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void GetBlinkSliders(float& Left, float& Right) const { Left = BlinkSliderL; Right = BlinkSliderR; }
	/** Manual gaze added to the eyes (degrees, yaw left positive, pitch up positive). */
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetManualGaze(float YawDeg, float PitchDeg) { ManualGazeYaw = YawDeg; ManualGazePitch = PitchDeg; }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void GetManualGaze(float& YawDeg, float& PitchDeg) const { YawDeg = ManualGazeYaw; PitchDeg = ManualGazePitch; }

	/** Expression presets: neutral, joy_confidence, anger, concern_sadness, surprise, pain, focus. */
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") bool ApplyPreset(FName Preset);
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void ClearAll();
	static const TArray<FName>& GetPresetNames();

	/** 1: face bones and curves of the playing clip drive the face and the code layer is added; 0: clip face ignored. */
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetClipFaceWeight(float W) { ClipFaceWeight = FMath::Clamp(W, 0.f, 1.f); }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") float GetClipFaceWeight() const { return ClipFaceWeight; }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void SetAutoBlink(bool bEnable) { bAutoBlink = bEnable; }
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") bool GetAutoBlink() const { return bAutoBlink; }
	/** Trigger one blink (both eyes) right now. */
	UFUNCTION(BlueprintCallable, Category = "Operative|Face") void TriggerBlink();

	/** Eye look computed by the action component (degrees, relative to the head, left/up positive). */
	void SetLookEyes(float YawDeg, float PitchDeg) { LookYaw = YawDeg; LookPitch = PitchDeg; }

	const FOperativeFaceState& GetState() const { return State; }
	const TArray<FName>& GetMorphNames() const { return MorphNames; }
	FString DescribeActive() const;
	FName GetActivePreset() const { return ActivePreset; }

private:
	void CacheLibrary();

	TArray<FName> MorphNames;
	TArray<FName> VisemeNames;
	TArray<float> MorphTarget;
	TArray<float> MorphCurrent;
	TArray<float> VisemeTarget;
	TArray<float> VisemeCurrent;
	float JawSlider = 0.f, TongueSlider = 0.f;
	float JawCurrent = 0.f, TongueCurrent = 0.f;
	float BlinkSliderL = 0.f, BlinkSliderR = 0.f;
	float ManualGazeYaw = 0.f, ManualGazePitch = 0.f;
	float LookYaw = 0.f, LookPitch = 0.f;
	float ClipFaceWeight = 1.f;
	bool bAutoBlink = true;
	float AutoBlinkTimer = 2.f;
	float AutoBlinkPhase = -1.f;   // <0: idle
	FRandomStream Random;
	FName ActivePreset = NAME_None;
	FOperativeFaceState State;
	bool bLibraryCached = false;
	TWeakObjectPtr<UOperativeLibrary> Library;
};
