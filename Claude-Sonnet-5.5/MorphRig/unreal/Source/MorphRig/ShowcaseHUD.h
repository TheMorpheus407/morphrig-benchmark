// MORPHRIG: HUD (canvas): state, clip, time, speed, event log with marker timeline, help overlay, speech subtitles with word highlight.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "ShowcaseHUD.generated.h"

UCLASS()
class MORPHRIG_API AShowcaseHUD : public AHUD
{
	GENERATED_BODY()
public:
	virtual void DrawHUD() override;

	/** Capture modes reduce the HUD (turntable: title only). */
	void SetHudLevel(int32 Level) { HudLevel = Level; }   // 0 none, 1 minimal, 2 full
	void SetCaption(const FString& C) { Caption = C; }

private:
	void Line(const FString& Text, float X, float Y, const FLinearColor& Color, float Scale = 1.f);
	void Rect(float X, float Y, float W, float H, const FLinearColor& Color);
	void DrawState(class AShowcasePlayerController* PC, class AOperativeCharacter* Op, class UOperativeActionComponent* A);
	void DrawTimeline(class UOperativeActionComponent* A, float X, float Y, float W);
	void DrawHelp(class AShowcasePlayerController* PC);
	void DrawSubtitle(class UOperativeActionComponent* A);
	float S = 1.f;
	float LineH = 14.f;
	int32 HudLevel = 2;
	FString Caption;
};
