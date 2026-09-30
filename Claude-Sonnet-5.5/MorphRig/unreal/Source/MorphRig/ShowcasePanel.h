// MORPHRIG: mouse driven control panel (Slate, built in C++, no editor authored widget assets).
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/Views/SListView.h"

class AShowcasePlayerController;
class SEditableTextBox;

class SShowcasePanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SShowcasePanel) {}
		SLATE_ARGUMENT(AShowcasePlayerController*, Controller)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	void NotifyViewerMode(bool bOn) { bViewerStation = bOn; }

private:
	TSharedRef<SWidget> BuildViewSection();
	TSharedRef<SWidget> BuildLocomotionSection();
	TSharedRef<SWidget> BuildActionSection();
	TSharedRef<SWidget> BuildHitSection();
	TSharedRef<SWidget> BuildBrowserSection();
	TSharedRef<SWidget> BuildFaceSection();
	void RebuildFilter();
	TSharedRef<ITableRow> GenerateClipRow(TSharedPtr<FName> Item, const TSharedRef<STableViewBase>& Owner);

	TWeakObjectPtr<AShowcasePlayerController> Ctrl;
	TArray<TSharedPtr<FName>> AllClips;
	TArray<TSharedPtr<FName>> FilteredClips;
	TSharedPtr<SListView<TSharedPtr<FName>>> ClipList;
	FString SearchText;
	bool bViewerStation = false;
	bool bPause = false;
};
