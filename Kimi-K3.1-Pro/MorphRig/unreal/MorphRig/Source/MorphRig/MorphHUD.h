#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "MorphHUD.generated.h"

class AMorphCharacter;
class STextBlock;
class SWrapBox;
class SVerticalBox;
class SWidget;

UCLASS()
class MORPHRIG_API UMorphHUD : public UUserWidget
{
    GENERATED_BODY()

public:
    void SetOperative(AMorphCharacter* InOperative);
    void SetCapturePresentation();
    void TogglePanel();
    bool IsPanelVisible() const { return bPanelVisible; }
    virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;

private:
    TSharedRef<SWidget> Button(const FString& Label, TFunction<void()> Action);
    TSharedRef<SWidget> Slider(const FString& Label, float Minimum, float Maximum, float Initial, TFunction<void(float)> Action);
    void Section(TSharedRef<SVerticalBox> Parent, const FString& Label);
    void Row(TSharedRef<SVerticalBox> Parent, std::initializer_list<TSharedRef<SWidget>> Widgets);
    void RebuildClipButtons(const FString& Filter);

    TWeakObjectPtr<AMorphCharacter> Operative;
    TSharedPtr<STextBlock> StatusText;
    TSharedPtr<STextBlock> DetailText;
    TSharedPtr<SWrapBox> ClipGrid;
    TSharedPtr<SWidget> PanelRoot;
    FString ClipFilter;
    float RefreshRemaining = 0.0f;
    bool bPanelVisible = true;
    bool bCapturePresentation = false;
};
