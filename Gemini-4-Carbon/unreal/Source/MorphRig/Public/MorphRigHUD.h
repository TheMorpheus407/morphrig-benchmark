#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "MorphRigTypes.h"
#include "MorphRigHUD.generated.h"

UENUM()
enum class EMorphRigHUDTab : uint8
{
	ActionsAndStates = 0,
	ClipBrowser96    = 1,
	FaceAndVisemes   = 2,
	ControlsHelp     = 3
};

UCLASS()
class MORPHRIG_API AMorphRigHUD : public AHUD
{
	GENERATED_BODY()

public:
	AMorphRigHUD();

	virtual void BeginPlay() override;
	virtual void DrawHUD() override;
	virtual void NotifyHitBoxClick(FName BoxName) override;

	void RenderOffscreenTelemetry(class UCanvas* TargetCanvas);
	bool bDrawingOffscreen = false;

	EMorphRigHUDTab ActiveTab = EMorphRigHUDTab::ActionsAndStates;
	FString BrowserSearchFilter;
	bool bSearchBoxFocused = false;
	int32 BrowserScrollOffset = 0;
	bool bShowHUDPanels = true;

	void AppendSearchChar(TCHAR Ch);
	void BackspaceSearch();
	void ClearSearch();
	void ScrollBrowser(int32 DeltaRows);

private:
	void DrawFilledBox(float X, float Y, float W, float H, const FLinearColor& Color);
	void DrawButton(float X, float Y, float W, float H, const FString& Label, FName HitName, bool bActive = false, const FLinearColor& Accent = FLinearColor(0.0f, 0.72f, 0.95f, 1.0f));
	void PollKeyboardShortcuts();

	TMap<FKey, bool> PrevKeyStates;
};
